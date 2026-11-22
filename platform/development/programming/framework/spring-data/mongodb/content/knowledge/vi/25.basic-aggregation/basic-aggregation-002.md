# Pipeline, stage, expression và luồng document qua từng bước

> **Chương:** Aggregation cơ bản  
> **Module:** `SPRING_DATA_MONGODB`

**Aggregation pipeline** là cách MongoDB xử lý dữ liệu bằng một chuỗi bước (*stage*). Mỗi bước nhận các document từ bước trước, áp dụng một phép lọc, biến đổi, gom nhóm hoặc sắp xếp, rồi đưa **kết quả trung gian** cho bước tiếp theo. Đây là một mô hình rất khác với việc gọi một câu `find` chỉ lọc và trả về nguyên document: trong pipeline, **hình dạng document có thể thay đổi ở từng stage**.

Trong Spring Data MongoDB, ta có thể viết pipeline bằng ngôn ngữ aggregation của MongoDB và biểu diễn các stage bằng **Aggregation API** cùng `MongoTemplate`, hoặc dùng `@Aggregation` trên repository khi phù hợp. Muốn dùng đúng các API đó, cần hiểu ba lớp khái niệm: **pipeline** (toàn bộ luồng xử lý), **stage** (một thao tác trên luồng) và **expression** (biểu thức tính toán trong một stage).

Bài học thuộc module `SPRING_DATA_MONGODB`: kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Trọng tâm bài này là **theo dõi luồng document qua từng bước** trước khi đi vào các dạng aggregation nâng cao.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả pipeline như một chuỗi stage và phân biệt stage với expression được dùng bên trong.
2. Theo dõi **số lượng** và **cấu trúc** document sau `$match`, `$project`, `$set`/`$addFields`, `$group`, `$sort` và `$limit`.
3. Hiểu cách tham chiếu field bằng `"$fieldName"`, biến đổi giá trị bằng `$multiply`, `$cond`, `$ifNull` và cách accumulator như `$sum` hoạt động trong `$group`.
4. Chuyển pipeline MongoDB từ `mongosh` sang Java với `Aggregation`, `Criteria` và `MongoTemplate.aggregate(...)`.
5. Phân biệt schema document nguồn với schema document kết quả; giải thích ý nghĩa `_id` sau grouping.
6. Kiểm thử dữ liệu trung gian, xử lý field thiếu/null, kiểm tra phạm vi tenant, index và `explain`.

## 2. Pipeline, stage và expression: ba khái niệm không được trộn lẫn

Một pipeline là **mảng các stage**, chạy theo thứ tự được khai báo:

```javascript
db.collection.aggregate([
  { $match: { status: "PAID" } },
  { $project: { status: 1, amount: 1 } },
  { $group: { _id: "$status", total: { $sum: "$amount" } } }
])
```

Ở cấp cao nhất của mỗi phần tử pipeline là **một stage** như `$match`, `$project` hoặc `$group`. Phần bên trong stage có thể chứa **expression**:

```javascript
{
  $project: {
    grossMinor: { $multiply: ["$unitPriceMinor", "$quantity"] }
  }
}
```

Trong đoạn này:

- `$project` là **stage** quyết định document đầu ra gồm các field nào và giá trị của chúng.
- `$multiply` là **expression** tính một giá trị từ hai toán hạng.
- `"$unitPriceMinor"` và `"$quantity"` là **tham chiếu giá trị của field** trong document hiện tại.
- `"grossMinor"` là **tên field đầu ra**. Viết `grossMinor: ...` không có nghĩa MongoDB đang tìm field nguồn cùng tên.

### 2.1. Sơ đồ luồng document

```text
Collection: sales_lines
       |
       | N document, đầy đủ các field gốc
       v
[$match]   Lọc tenant và trạng thái
       |
       | Chỉ document đạt điều kiện; schema gần như không đổi
       v
[$project] Giữ status, tính grossMinor = unitPriceMinor × quantity
       |
       | Cùng số document nhưng schema mới
       v
[$group]   Gom các document theo status, tính count và total
       |
       | Mỗi nhóm trở thành một document tổng hợp
       v
[$sort]    Sắp xếp các document tổng hợp
       |
       | Không đổi số document, chỉ đổi thứ tự
       v
[$limit]   Lấy tối đa K document đầu
       |
       v
Kết quả: các document báo cáo, KHÔNG phải entity nguồn
```

**Nguyên tắc quan trọng:** stage phía sau chỉ được sử dụng những field còn tồn tại trong **đầu ra của stage trước**. Nếu `$project` đã loại `unitPriceMinor`, một stage phía sau không thể tự tính lại bằng `"$unitPriceMinor"` như thể field gốc vẫn còn.

### 2.2. Bảng phân loại

| Thành phần | Vị trí | Vai trò | Ví dụ |
| --- | --- | --- | --- |
| Pipeline | Mảng các stage | Định nghĩa luồng xử lý từ đầu đến cuối | `[{$match:...}, {$group:...}]` |
| Stage | Một phần tử trong pipeline | Lọc, biến đổi, mở rộng, gom nhóm hoặc xuất dữ liệu | `$match`, `$project`, `$group` |
| Expression | Bên trong stage | Tính giá trị, quyết định logic, tham chiếu field | `$multiply`, `$cond`, `$ifNull` |
| Accumulator | Trong ngữ cảnh như `$group` | Gộp nhiều giá trị thành kết quả nhóm | `$sum`, `$avg`, `$max` |
| Group key | `_id` trong `$group` | Xác định document nào cùng nhóm | `_id: "$status"` |
| Output document | Kết quả của stage cuối | Dữ liệu trả về cho ứng dụng | `{_id:"PAID", totalMinor:105000}` |

Không phải mọi toán tử có tiền tố `$` đều là stage. Ví dụ `$multiply` và `$cond` được đặt trong expression; `$sum` có các cách dùng theo ngữ cảnh; `$sort` là một stage. Phải đọc **vị trí cú pháp** của toán tử.

## 3. Dữ liệu xuyên suốt: dòng hàng bán được

Một cửa hàng cần báo cáo **doanh thu sơ bộ theo trạng thái dòng hàng**. Collection `sales_lines` chứa **mỗi document là một dòng hàng**, không phải một đơn hàng hoàn chỉnh. Vì vậy `count` ở các ví dụ dưới đây là **số dòng hàng**, không phải số đơn hàng duy nhất.

File `SalesLine.java`:

```java
package com.example.shop.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "sales_lines")
public record SalesLine(
    @Id String id,
    String tenantId,
    String status,
    String channel,
    long unitPriceMinor,
    int quantity
) {}
```

`unitPriceMinor` là số tiền theo đơn vị nguyên nhỏ nhất được hệ thống thống nhất (ví dụ đồng Việt Nam), `quantity` là số lượng, và `grossMinor = unitPriceMinor * quantity` là giá trị sơ bộ. Bài không tự tính thuế, hoàn tiền, khuyến mại hoặc tỷ giá; nếu nghiệp vụ cần **doanh thu ghi nhận**, phải định nghĩa đúng nguồn và các phép điều chỉnh thay vì chỉ nhân giá với số lượng.

### 3.1. Dữ liệu mẫu bằng mongosh

**Chỉ chạy trên MongoDB dành riêng cho thực hành/kiểm thử:**

```javascript
use shop

db.sales_lines.insertMany([
  { _id: "A-01", tenantId: "TENANT-A", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(12000), quantity: 2 },
  { _id: "A-02", tenantId: "TENANT-A", status: "PAID",
    channel: "store", unitPriceMinor: NumberLong(55000), quantity: 1 },
  { _id: "A-03", tenantId: "TENANT-A", status: "NEW",
    channel: "web",   unitPriceMinor: NumberLong(5000),  quantity: 3 },
  { _id: "A-04", tenantId: "TENANT-A", status: "CANCELLED",
    channel: "store", unitPriceMinor: NumberLong(30000), quantity: 1 },
  { _id: "A-05", tenantId: "TENANT-A", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(8000),  quantity: 2 },
  { _id: "A-06", tenantId: "TENANT-A", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(2000),  quantity: 5 },
  { _id: "A-07", tenantId: "TENANT-A", status: "NEW",
    channel: "store", unitPriceMinor: NumberLong(20000), quantity: 1 },
  { _id: "B-01", tenantId: "TENANT-B", status: "PAID",
    channel: "web",   unitPriceMinor: NumberLong(10000), quantity: 4 }
])
```

### 3.2. Bảng giá trị kỳ vọng

| ID | Tenant | Trạng thái | Kênh | Đơn giá | SL | Giá trị dòng |
| --- | --- | --- | --- | ---: | ---: | ---: |
| A-01 | A | PAID | web | 12.000 | 2 | 24.000 |
| A-02 | A | PAID | store | 55.000 | 1 | 55.000 |
| A-03 | A | NEW | web | 5.000 | 3 | 15.000 |
| A-04 | A | CANCELLED | store | 30.000 | 1 | 30.000 |
| A-05 | A | PAID | web | 8.000 | 2 | 16.000 |
| A-06 | A | PAID | web | 2.000 | 5 | 10.000 |
| A-07 | A | NEW | store | 20.000 | 1 | 20.000 |
| B-01 | B | PAID | web | 10.000 | 4 | 40.000 |

Mục tiêu báo cáo:

- Chỉ đọc dữ liệu **TENANT-A**; không được cộng doanh thu của B-01.
- Chỉ xét `PAID` và `NEW`; loại `CANCELLED`.
- Tính giá trị từng dòng, sau đó đếm và cộng theo trạng thái.
- Trả kết quả từ tổng lớn đến nhỏ.

Kết quả mong đợi: **PAID = 4 dòng, tổng 105.000**; **NEW = 2 dòng, tổng 35.000**.

## 4. Pipeline hoàn chỉnh trong MongoDB

Viết pipeline ngay tại tầng MongoDB giúp chúng ta nhìn thấy **ngữ nghĩa cần đạt** trước khi chuyển sang Java:

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      _id: 0,
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  {
    $group: {
      _id: "$status",
      lineCount: { $sum: 1 },
      totalMinor: { $sum: "$grossMinor" }
    }
  },
  {
    $sort: {
      totalMinor: -1,
      _id: 1
    }
  },
  { $limit: 2 }
])
```

Đầu ra:

```javascript
[
  { _id: "PAID", lineCount: 4, totalMinor: NumberLong(105000) },
  { _id: "NEW",  lineCount: 2, totalMinor: NumberLong(35000) }
]
```

Các giá trị số đầu ra trong `mongosh` có thể hiển thị ở dạng BSON số khác nhau tùy kiểu đầu vào/quy tắc nâng kiểu; bảng trên dùng `NumberLong` để nhấn mạnh các khoản tiền đã được lưu theo số nguyên dài. Hợp đồng quan trọng là **giá trị, độ chính xác và cách xử lý số**, không phải trình bày string đúng một kiểu ở mọi shell/driver.

### 4.1. Luồng dữ liệu sau từng stage

| Bước | Stage | Số document | Hình dạng document sau bước | Điều cần nhớ |
| --- | --- | ---: | --- | --- |
| Nguồn | Collection `sales_lines` | 8 | `_id, tenantId, status, channel, unitPriceMinor, quantity` | Dòng hàng gốc |
| 1 | `$match` | 6 | Các field gốc của 6 dòng tenant A, PAID/NEW | **Lọc**; không tính gross |
| 2 | `$project` | 6 | `status, grossMinor` | **Đổi schema**; mất `tenantId`, `channel`, `quantity` |
| 3 | `$group` | 2 | `_id, lineCount, totalMinor` | **Gom** 6 dòng thành 2 nhóm |
| 4 | `$sort` | 2 | Không đổi field | **Đổi thứ tự** nhóm |
| 5 | `$limit` | 2 | Không đổi field | Chỉ nhận tối đa 2 nhóm đầu |

Lệnh `$limit: 2` trong ví dụ chưa loại nhóm nào vì chỉ có hai trạng thái. Nếu đổi thành `$limit: 1`, kết quả chỉ có nhóm `PAID`. Đây là cách dễ quan sát rằng `$limit` áp **lên luồng đang có ở đúng vị trí đó**, không nhất thiết lên document gốc.

## 5. Quan sát thật kỹ từng stage

### 5.1. Bước 1 — $match: document nào đi tiếp?

`$match` dùng cú pháp filter MongoDB tương tự `find`:

```javascript
{
  $match: {
    tenantId: "TENANT-A",
    status: { $in: ["PAID", "NEW"] }
  }
}
```

Các điều kiện đặt cùng cấp được kết hợp theo **AND**. Vì vậy:

- `tenantId` phải là `TENANT-A`;
- `status` phải thuộc tập `PAID` hoặc `NEW`.

Sau `$match`, sáu document còn lại là **A-01, A-02, A-03, A-05, A-06, A-07**. A-04 bị loại do `CANCELLED`; B-01 bị loại do tenant khác. Những document đi tiếp vẫn có đầy đủ field gốc, vì `$match` không có nhiệm vụ tạo schema đầu ra mới.

Có thể chạy riêng phần đầu để kiểm tra:

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  }
])
```

**Phạm vi tenant là bất biến an toàn**: không đặt `tenantId` chỉ vào một nhánh của `$or` rồi để nhánh khác tự do đọc dữ liệu tenant khác. Trong ứng dụng thật, tenant phải được lấy từ hoặc xác minh với ngữ cảnh phân quyền, không tin chuỗi do client cung cấp.

### 5.2. Bước 2 — $project: từng document biến thành gì?

```javascript
{
  $project: {
    _id: 0,
    status: 1,
    grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
    }
  }
}
```

`status: 1` nói rằng giữ giá trị field `status`; `_id: 0` loại field định danh khỏi **kết quả tạm thời**; `grossMinor` được tạo từ biểu thức tính toán.

Luồng sau bước 2:

| Document nguồn | `status` đầu ra | `grossMinor` đầu ra | Phép tính |
| --- | --- | ---: | --- |
| A-01 | PAID | 24.000 | 12.000 × 2 |
| A-02 | PAID | 55.000 | 55.000 × 1 |
| A-03 | NEW | 15.000 | 5.000 × 3 |
| A-05 | PAID | 16.000 | 8.000 × 2 |
| A-06 | PAID | 10.000 | 2.000 × 5 |
| A-07 | NEW | 20.000 | 20.000 × 1 |

Ví dụ một output document:

```javascript
{
  status: "PAID",
  grossMinor: NumberLong(24000)
}
```

Ở thời điểm này, mỗi document **không còn** `tenantId`, `channel`, `unitPriceMinor` hoặc `quantity`. Stage phía sau phải dựa vào `status` và `grossMinor`, hoặc phải thay đổi projection trước đó nếu còn cần thêm field.

#### Vì sao _id: 0?

`$project` giữ `_id` mặc định trừ khi loại nó. Trong báo cáo nhóm theo trạng thái, `_id` của dòng hàng nguồn không cần thiết sau `$project`, vì `$group` sẽ tạo **`_id` mới cho nhóm**. Việc loại `_id` ở bước project không hề xóa ID của document gốc trong collection.

**Quy tắc projection:** nhìn chung không trộn phép *include* và *exclude* các field thường trong cùng `$project`; ngoại lệ quen thuộc là có thể loại `_id` khi đang include những field khác. Expression tính field mới thuộc projection và phải được kiểm thử theo schema đầu vào.

### 5.3. Bước 3 — $group: nhiều document thành một nhóm

```javascript
{
  $group: {
    _id: "$status",
    lineCount: { $sum: 1 },
    totalMinor: { $sum: "$grossMinor" }
  }
}
```

`_id: "$status"` là **khóa nhóm**. Mọi dòng có cùng giá trị status đi vào một nhóm. `$sum: 1` tăng bộ đếm lên 1 cho mỗi document đến nhóm; `$sum: "$grossMinor"` cộng giá trị tính ở bước project cho từng document.

Nội dung nhóm:

```text
PAID:
  A-01  24.000
  A-02  55.000
  A-05  16.000
  A-06  10.000
  -----------------
  lineCount       4
  totalMinor 105.000

NEW:
  A-03  15.000
  A-07  20.000
  -----------------
  lineCount       2
  totalMinor  35.000
```

Document đầu ra từ `$group`:

```javascript
{
  _id: "PAID",
  lineCount: 4,
  totalMinor: NumberLong(105000)
}
```

**Lúc này `_id` không còn là ID dòng hàng.** Nó là **khóa nhóm**. Các field `status` và `grossMinor` của từng dòng không còn tồn tại dưới dạng field trực tiếp trên document kết quả nếu chưa được tạo lại bằng accumulator hoặc projection.

Nếu cần đổi `_id` thành tên thân thiện hơn ở cuối:

```javascript
{
  $project: {
    _id: 0,
    status: "$_id",
    lineCount: 1,
    totalMinor: 1
  }
}
```

Stage này phải được đặt **sau `$group`**, vì nó tham chiếu `_id` mới của nhóm.

### 5.4. Bước 4 — $sort: sắp xếp document hiện tại

```javascript
{ $sort: { totalMinor: -1, _id: 1 } }
```

`-1` là giảm dần, `1` là tăng dần. Ở đây ta sắp xếp **hai document tổng hợp**, không phải sáu dòng hàng ban đầu. `_id` làm khóa phụ giúp thứ tự quyết định khi hai nhóm có cùng tổng.

**Không mặc định kết quả của `$group` có thứ tự ổn định.** Nếu phía Java/API cần order cụ thể, thêm `$sort`. Nếu `$sort` nằm **trước** `$group`, việc sắp xếp dòng nguồn thường không đảm bảo thứ tự đầu ra của nhóm.

### 5.5. Bước 5 — $limit: giới hạn tại đúng điểm đặt

```javascript
{ $limit: 2 }
```

`$limit` chỉ giữ tối đa hai document **sau khi** đã group và sort. Vì có đúng hai nhóm nên kết quả không đổi. Nếu muốn báo cáo một trạng thái có tổng cao nhất, thay thành `$limit: 1`.

Không được đẩy `$limit` tùy ý lên trước `$group`:

```javascript
// PHẢN VÍ DỤ: đây không phải cách tính tổng của TẤT CẢ dòng.
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A", status: "PAID" } },
  { $limit: 2 },
  { $group: {
      _id: "$status",
      totalMinor: {
        $sum: { $multiply: ["$unitPriceMinor", "$quantity"] }
      }
  }}
])
```

Pipeline trên chỉ tính tổng của **hai document bất kỳ đầu luồng** trong nhóm đã lọc, chứ không phải bốn dòng PAID. Vì chưa có `$sort`, không nên giả định hai document được lấy là A-01/A-02 trong mọi lần chạy. Ngay cả khi thêm sort ổn định, kết quả vẫn là tổng của **hai dòng đầu**, không phải toàn bộ doanh thu.

## 6. $addFields / $set, $project và $unset khác nhau thế nào?

Ba stage này đều có thể biến đổi schema, nhưng có ý nghĩa khác nhau:

| Stage | Mục đích | Field gốc không nhắc tới |
| --- | --- | --- |
| `$project` | Chọn/đổi tên/tính field trong kết quả | Thường **bị loại** khi dùng inclusion projection |
| `$addFields` | Thêm field mới hoặc ghi đè field đã có | **Được giữ** |
| `$set` (aggregation stage) | Alias của `$addFields` | **Được giữ** |
| `$unset` (aggregation stage) | Loại field ra khỏi luồng hiện tại | Các field khác được giữ |

### 6.1. Thêm trường tính toán mà vẫn giữ dữ liệu gốc

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $addFields: {
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  }
])
```

Với A-01, kết quả có cả `_id`, `tenantId`, `status`, `channel`, `unitPriceMinor`, `quantity` **và thêm `grossMinor: 24000`**. Đây là lựa chọn tốt nếu stage sau vẫn cần nhiều field gốc.

Có thể viết tương đương:

```javascript
{
  $set: {
    grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
    }
  }
}
```

**Cảnh báo:** `$set` là stage trong aggregation pipeline ở ví dụ này; `$set` cũng là **update operator** khi nằm trong lệnh update dữ liệu. Hai ngữ cảnh có cú pháp gần nhau nhưng mục đích khác nhau. Một pipeline đọc thông thường với `$set` **không ghi ngược** vào collection.

### 6.2. Loại field khỏi kết quả tạm

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $unset: ["channel", "quantity"] }
])
```

Document còn lại không có `channel`/`quantity`, nhưng các field nguồn trên database **không hề bị xóa**. `$unset` là phép biến đổi trên luồng aggregation. Nếu pipeline sau đó cần `quantity`, ta phải thay đổi thứ tự stage hoặc không unset quá sớm.

## 7. Expression là phép tính bên trong stage

Expression có thể sử dụng giá trị của document hiện tại, hằng số, các toán tử số học, so sánh, chuỗi, ngày tháng hoặc điều kiện. Một expression **không tự biến thành stage riêng**.

### 7.1. Tham chiếu field và hằng số

```javascript
{
  $project: {
    unitPrice: "$unitPriceMinor",
    quantity: 1,
    fixedFee: { $literal: 1000 },
    grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
    }
  }
}
```

`"$unitPriceMinor"` đọc field nguồn. `$literal` biểu diễn giá trị hằng theo mục đích. Trong expression, một string bắt đầu bằng `$` thường được hiểu là field path/biến, nên nếu thực sự muốn output string bắt đầu bằng dấu `$`, có thể cần `$literal`.

### 7.2. $cond: quyết định giá trị theo điều kiện

Gắn nhãn dòng có số lượng lớn (từ 3 trở lên):

```javascript
{
  $project: {
    _id: 1,
    quantity: 1,
    sizeLabel: {
      $cond: [
        { $gte: ["$quantity", 3] },
        "MULTI",
        "SINGLE"
      ]
    }
  }
}
```

Các dòng A-03 (quantity 3) và A-06 (quantity 5) mang `MULTI`; A-01 (quantity 2) mang `SINGLE`. Đây là một expression tạo **giá trị field mới**, không tự lọc document. Nếu muốn loại dòng có số lượng nhỏ, cần thêm `$match` phù hợp.

### 7.3. $ifNull: gán giá trị dự phòng

Một document legacy thiếu `channel`:

```javascript
{
  $project: {
    _id: 1,
    channelLabel: {
      $ifNull: ["$channel", "unknown"]
    }
  }
}
```

`$ifNull` dùng giá trị dự phòng nếu expression đầu là `null` hoặc missing theo ngữ nghĩa MongoDB. Điều này **không chứng minh** giá trị `unknown` có cùng ý nghĩa nghiệp vụ với một channel đã được xác minh. Trong báo cáo, cần phân biệt “chưa có dữ liệu” và “đã xác định là một loại kênh”.

### 7.4. Accumulator và expression không giống nhau

Trong `$group`:

```javascript
{
  $group: {
    _id: "$status",
    count: { $sum: 1 },
    totalMinor: {
      $sum: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  }
}
```

`$sum` ở vị trí này là **accumulator** cộng qua **nhiều document của cùng nhóm**. `$multiply` bên trong tính giá trị **cho từng document** trước khi cộng.

Lưu ý có thể đặt phép nhân **trực tiếp trong `$group`** như trên, không nhất thiết tạo `grossMinor` bằng `$project` trước. Tuy nhiên, pipeline có `$project` riêng ở đầu bài hữu ích cho việc học và debug từng bước.

### 7.5. Thiết kế kiểu số an toàn

Nếu `unitPriceMinor` là BSON Int64 và `quantity` là số nguyên, phép nhân và phép cộng phải được kiểm tra để tránh overflow khi dữ liệu lớn. Không nên trộn Double với số tiền cần độ chính xác tuyệt đối; nếu nghiệp vụ cần phần lẻ/đa tiền tệ, chọn kiểu số phù hợp (ví dụ Decimal128 cùng quy tắc làm tròn), không giả định `double` luôn an toàn.

Đối với dữ liệu lỗi kiểu như `unitPriceMinor: "12000"`, biểu thức `$multiply` có thể gây lỗi, chứ không phải luôn tự chuyển string thành number. Cần validate schema, migration hoặc dùng các expression chuyển kiểu như `$convert` với chính sách `onError`/`onNull` rõ ràng.

## 8. $unwind làm thay đổi *số lượng document* như thế nào?

Trong pipeline chính, `$match` loại một số document, `$project` giữ số document, còn `$group` gom nhiều document thành ít document hơn. Nhưng có stage **tăng số document**, ví dụ `$unwind`.

Giả sử có dữ liệu khác:

```javascript
{
  _id: "ORDER-X",
  tenantId: "TENANT-A",
  tags: ["web", "priority", "campaign"],
  status: "PAID"
}
```

Pipeline:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $unwind: "$tags" },
  { $project: { _id: 1, status: 1, tag: "$tags" } }
])
```

Một document `ORDER-X` sau `$unwind` trở thành **ba document đầu ra**:

```javascript
{ _id: "ORDER-X", status: "PAID", tag: "web" }
{ _id: "ORDER-X", status: "PAID", tag: "priority" }
{ _id: "ORDER-X", status: "PAID", tag: "campaign" }
```

Các document này mang cùng `_id` vì chúng là các **bản ghi tạm trong luồng**, không phải insert ba document mới vào collection. Nếu group/count sau unwind, một order ba tag có thể đóng góp **ba lượt** thay vì một; cần phân biệt mục đích “đếm tag” với “đếm đơn hàng”.

### 8.1. Mảng rỗng hoặc field thiếu

Mặc định, `$unwind` có thể loại document nếu đường dẫn array là null, missing hoặc mảng rỗng. Nếu muốn giữ những document đó trong luồng, cấu hình:

```javascript
{
  $unwind: {
    path: "$tags",
    preserveNullAndEmptyArrays: true
  }
}
```

Khi bật tùy chọn này, các document thiếu/không có phần tử cũng có thể được giữ lại với cách biểu diễn field phù hợp. **Không tự coi việc giữ lại đồng nghĩa chúng có một tag thực**. Khi group theo tag, cần một chính sách riêng cho null/missing.

### 8.2. $lookup không tự nhân số document cấp ngoài

`$lookup` thông thường thêm **mảng kết quả join** vào mỗi document nguồn. Nó chưa nhất thiết làm tăng số document cấp ngoài. Khi kết hợp `$lookup` và `$unwind` trên mảng join, lúc đó một document gốc có thể trở thành nhiều document. Đây là lý do phân tích **cardinality** của mỗi stage rất quan trọng khi làm báo cáo nhiều collection.

## 9. $group theo một khóa hoặc nhiều khóa

### 9.1. Group theo status

```javascript
{
  $group: {
    _id: "$status",
    lineCount: { $sum: 1 }
  }
}
```

Sau `$match` của pipeline chính, cách này tạo hai document nhóm: `PAID` và `NEW`.

### 9.2. Group theo cặp status và channel

Nếu muốn chia theo **trạng thái và kênh bán**, nhóm bằng một object:

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $group: {
      _id: {
        status: "$status",
        channel: "$channel"
      },
      lineCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.status": 1, "_id.channel": 1 } }
])
```

Kết quả:

```javascript
[
  { _id: { status: "NEW",  channel: "store" }, lineCount: 1 },
  { _id: { status: "NEW",  channel: "web"   }, lineCount: 1 },
  { _id: { status: "PAID", channel: "store" }, lineCount: 1 },
  { _id: { status: "PAID", channel: "web"   }, lineCount: 3 }
]
```

**Điểm khác biệt:** `_id` của document tổng hợp giờ là **object gồm hai khóa**, không phải một string. Một Java DTO chỉ khai báo `String id` sẽ không phù hợp để nhận kết quả này nếu không có mapping/chuyển đổi đúng.

Không được chạy `$project` loại `channel` trước rồi mới group theo channel. Nếu field đã mất trong luồng, khóa nhóm sẽ không còn phân biệt kênh đúng như ý định.

### 9.3. Group tất cả document vào một nhóm

Nếu cần một tổng duy nhất trong phạm vi đã lọc:

```javascript
{
  $group: {
    _id: null,
    lineCount: { $sum: 1 },
    totalMinor: {
      $sum: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  }
}
```

Với sáu dòng tenant A có trạng thái PAID/NEW, kết quả tổng là `140.000` và `lineCount = 6`. Không đặt `tenantId` trong group key có thể hợp lý **nếu trước đó đã giới hạn tenant một cách bắt buộc**. Nếu quên `$match` tenant, tổng sẽ cộng dữ liệu của các tenant khác, gây sai báo cáo và có thể lộ thông tin.

### 9.4. Đếm document khác với đếm đơn hàng

Vì collection `sales_lines` chứa mỗi dòng hàng là một document:

```javascript
lineCount: { $sum: 1 }
```

đếm **số dòng**, không đếm đơn hàng. Nếu một đơn chứa ba dòng thì nó đóng góp ba lượt. Muốn đếm **số đơn hàng duy nhất**, dữ liệu phải có khóa như `orderId` và pipeline phải nhóm/đếm distinct theo khóa đó. Đừng đặt tên `orderCount` cho một accumulator thực tế chỉ đếm line items.

## 10. Thứ tự stage ảnh hưởng cả ý nghĩa lẫn chi phí

Hai pipeline không tương đương chỉ vì chúng chứa cùng các tên stage.

### 10.1. $match sớm khi điều kiện dựa trên field gốc

Thường nên lọc tenant và trạng thái **trước khi** làm phép nhân và group:

```javascript
[
  { $match: { tenantId: "TENANT-A", status: "PAID" } },
  { $project: { grossMinor: {
      $multiply: ["$unitPriceMinor", "$quantity"]
  } } },
  { $group: { _id: null, total: { $sum: "$grossMinor" } } }
]
```

Ít document hơn đi vào các stage tính toán. Điều kiện `$match` đầu pipeline cũng có cơ hội tận dụng index thích hợp trên collection nguồn.

### 10.2. Filter theo field tính toán phải đặt sau khi field xuất hiện

Muốn lấy những dòng có `grossMinor >= 20.000`:

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $set: {
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
  }},
  { $match: { grossMinor: { $gte: NumberLong(20000) } } }
])
```

Nếu đưa điều kiện `grossMinor` lên **trước** `$set` trong dữ liệu mẫu (vốn chưa lưu field này), kết quả không có dòng nào khớp. Bộ tối ưu truy vấn của MongoDB có thể tự sắp xếp lại một số stage khi điều kiện độc lập, nhưng ứng dụng vẫn phải thiết kế **ngữ nghĩa phụ thuộc field** đúng.

### 10.3. $limit và $skip ở các vị trí khác nhau

```javascript
// A: lấy tối đa 2 DÒNG trước khi group.
[
  { $match: { tenantId: "TENANT-A" } },
  { $limit: 2 },
  { $group: { _id: "$status", lines: { $sum: 1 } } }
]

// B: group TẤT CẢ dòng trước khi lấy 2 NHÓM.
[
  { $match: { tenantId: "TENANT-A" } },
  { $group: { _id: "$status", lines: { $sum: 1 } } },
  { $sort: { lines: -1, _id: 1 } },
  { $limit: 2 }
]
```

Pipeline A tính trên một **mẫu có hai dòng**; pipeline B tính nhóm trên **toàn tập tenant A**, rồi giữ hai nhóm. Nếu cần phân trang output nhóm, thường phải group xong, sort ổn định, rồi mới `$skip`/`$limit` theo hợp đồng báo cáo. Offset sâu trên dữ liệu nhiều nhóm vẫn có thể tốn chi phí; cân nhắc kỹ yêu cầu paging.

### 10.4. $sort trước và sau group có mục đích khác nhau

- `$sort` **trước `$group`** tác động thứ tự các document đi vào phép gom. Trong một số thuật toán dùng accumulator phụ thuộc thứ tự như `$first`, thứ tự đầu vào có ý nghĩa.
- `$sort` **sau `$group`** sắp xếp **những document tổng hợp** mà API sẽ nhận.

Nếu cần trạng thái có doanh thu cao nhất, phải sort theo `totalMinor` **sau khi totalMinor được tính**, không thể sort theo field tổng này khi nó chưa xuất hiện.

## 11. Biểu diễn pipeline bằng Spring Data MongoDB Aggregation API

Trong Java, `Aggregation` là container của các `AggregationOperation`. `MongoTemplate.aggregate(...)` gửi pipeline đến MongoDB và ánh xạ kết quả sang `Document` hoặc DTO. Ta giữ mô hình dữ liệu và kỳ vọng giống mongosh để đối chiếu trực tiếp.

Các import thường dùng:

```java
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
```

### 11.1. Ví dụ service hoàn chỉnh

File `SalesAnalyticsService.java`:

```java
package com.example.shop.sales;

import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.stereotype.Service;

@Service
public class SalesAnalyticsService {

    private final MongoTemplate template;

    public SalesAnalyticsService(MongoTemplate template) {
        this.template = template;
    }

    public record RevenueByStatus(
        String status, long lineCount, long totalMinor) {}

    public List<RevenueByStatus> summarizeTenant(
            String permittedTenantId) {

        if (permittedTenantId == null
                || permittedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant không hợp lệ");
        }

        Aggregation pipeline = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is(permittedTenantId)
                    .and("status").in("PAID", "NEW")
            ),
            Aggregation.project("status")
                .andExpression("unitPriceMinor * quantity")
                .as("grossMinor")
                .andExclude("_id"),
            Aggregation.group("status")
                .count().as("lineCount")
                .sum("grossMinor").as("totalMinor"),
            Aggregation.sort(
                Sort.by(
                    Sort.Order.desc("totalMinor"),
                    Sort.Order.asc("_id")
                )
            ),
            Aggregation.limit(2)
        );

        AggregationResults<Document> aggregated =
            template.aggregate(
                pipeline, "sales_lines", Document.class);

        return aggregated.getMappedResults().stream()
            .map(doc -> new RevenueByStatus(
                doc.getString("_id"),
                ((Number) doc.get("lineCount")).longValue(),
                ((Number) doc.get("totalMinor")).longValue()
            ))
            .toList();
    }
}
```

**Dòng chảy giữa Java và MongoDB:**

1. `Aggregation.match(...)` diễn đạt `$match` giới hạn tenant/trạng thái.
2. `Aggregation.project("status").andExpression("unitPriceMinor * quantity")` dùng biểu thức số học kiểu SpEL của Spring Data để tạo `grossMinor` (tương đương ý nghĩa `$multiply`).
3. `Aggregation.group("status").count().as(...).sum("grossMinor").as(...)` tạo các accumulator trong `$group`.
4. `Aggregation.sort(...)` và `Aggregation.limit(2)` sắp xếp, giới hạn **kết quả nhóm**.
5. `template.aggregate(...)` thực thi; `AggregationResults<Document>` chứa document báo cáo, không phải danh sách `SalesLine` gốc.

Kỳ vọng gọi:

```java
List<SalesAnalyticsService.RevenueByStatus> result =
    service.summarizeTenant("TENANT-A");

// result:
// RevenueByStatus("PAID", 4, 105000)
// RevenueByStatus("NEW",  2, 35000)
```

`service` là instance `SalesAnalyticsService` được inject. Bộ lọc tenant phải được xây từ tenant đã xác minh quyền ở tầng service/controller, không cho phép client chọn tùy ý tenant khác rồi gọi thẳng phương thức này.

### 11.2. Vì sao output không trả về SalesLine?

Sau `$group`, document chỉ có `_id` (chứa giá trị status), `lineCount` và `totalMinor`. Nó **không còn** `tenantId`, `quantity`, `unitPriceMinor` hay ID dòng hàng. Nếu cố ánh xạ kết quả vào `SalesLine`, entity có thể thiếu nhiều field hoặc mang giá trị mặc định sai.

Ta có hai hướng:

- **`Document`** để quan sát cấu trúc BSON đầu ra, hữu ích khi học, debug hoặc xây pipeline phức tạp.
- **DTO/read model** tương ứng kết quả báo cáo, với mapping đúng field `_id` hoặc thêm một `$project` đổi `_id` thành `status` trước khi ánh xạ.

Ở ví dụ trên, service nhận `Document` và chuyển sang record kết quả rõ ràng. Cast qua `Number` tránh giả định `lineCount` luôn là `Integer` hay `Long` ở mọi trường hợp. Với sản phẩm thật, có thể cấu hình typed output trực tiếp sau khi đã thống nhất schema và converter.

### 11.3. Nhớ mapping tên field

Giả sử entity Java dùng:

```java
@Field("unit_price_minor")
private long unitPriceMinor;
```

Spring Data Aggregation API có thể ánh xạ property Java sang field BSON thông qua metadata khi dùng typed aggregation/input type. Nhưng **raw pipeline trong mongosh** phải sử dụng đúng tên field BSON `unit_price_minor`. Khi kết hợp stage dạng raw JSON với typed DSL, cần kiểm tra pipeline cuối cùng để không áp nhầm hai quy ước.

Ví dụ chính cố ý đặt tên property Java và field BSON giống nhau. Khi dự án thay đổi `@Field` hoặc custom converter, hãy viết integration test xác minh phép tính trên BSON thực tế, không chỉ nhìn mã Java.

## 12. Cách debug pipeline bằng những kết quả trung gian

Khi một báo cáo trả kết quả sai, đừng thay đổi tất cả stage cùng lúc. Hãy chạy **những pipeline tiền tố**: chỉ stage đầu; hai stage đầu; ba stage đầu; rồi thêm sort/limit.

### 12.1. Kiểm tra stage lọc

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  { $count: "matchedLines" }
])
// [{ matchedLines: 6 }]
```

`$count` ở đây là một stage độc lập dùng để **đếm số document đã đến nó**. Nó thay toàn bộ luồng kết quả bằng một document đếm (hoặc không tạo document nếu đầu vào rỗng, tùy ngữ nghĩa của stage). Không đặt `$count` vào giữa pipeline chính rồi mong các field nguồn vẫn còn cho `$project` phía sau.

### 12.2. Kiểm tra biểu thức tính

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  { $sort: { _id: 1 } }
])
```

Trong debug, **tạm giữ `_id`** để biết dòng nào tạo ra giá trị sai. Khi xác nhận phép nhân đúng trên cả sáu dòng, mới quay lại bản projection báo cáo có thể loại ID để giảm dữ liệu trung gian.

### 12.3. Kiểm tra group trước sort/limit

```javascript
db.sales_lines.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  {
    $group: {
      _id: "$status",
      lineCount: { $sum: 1 },
      totalMinor: { $sum: "$grossMinor" }
    }
  }
])
```

Ở bước này phải có **hai nhóm** với các tổng đúng, dù thứ tự trả về có thể khác. Chỉ khi đó mới thêm `$sort` và `$limit` để hoàn thiện cách trình bày.

### 12.4. Kiểm tra kiểu dữ liệu và null/missing

Nếu tổng bằng 0 hoặc thấp hơn dự kiến:

```javascript
db.sales_lines.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      _id: 1,
      priceType: { $type: "$unitPriceMinor" },
      quantityType: { $type: "$quantity" },
      statusType: { $type: "$status" }
    }
  }
])
```

Lệnh này giúp quan sát các kiểu `long`, `int`, `string`, `null`, `missing` tùy BSON thực tế. Nếu một writer cũ lưu giá dạng string, không nên vội sửa `$group`; cần chuẩn hóa dữ liệu hoặc xác định rõ cách chuyển kiểu và lỗi khi chuyển.

## 13. Kiểm thử tích hợp trên MongoDB thực

Mock `MongoTemplate` hoặc kiểm thử chỉ so sánh một chuỗi JSON **không chứng minh** server thực hiện `$multiply`/`$group` theo dữ liệu thực. Nên tạo database test cô lập, chèn BSON thật và xác minh cả số document giữa các stage lẫn kết quả cuối.

### 13.1. Fixture JUnit 5 và AssertJ

Ví dụ dùng `@DataMongoTest` của Spring Boot (đối chiếu package import theo phiên bản dự án). File `SalesAggregationIntegrationTest.java`:

```java
package com.example.shop.sales;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class SalesAggregationIntegrationTest {

    @Autowired
    MongoTemplate template;

    private static Document line(
            String id, String tenant, String status,
            String channel, long price, int quantity) {

        return new Document("_id", id)
            .append("tenantId", tenant)
            .append("status", status)
            .append("channel", channel)
            .append("unitPriceMinor", price)
            .append("quantity", quantity);
    }

    @BeforeEach
    void seed() {
        // Chỉ sử dụng MongoDB TEST cô lập, không dùng database chung.
        var collection = template.getCollection("sales_lines");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            line("A-01", "TENANT-A", "PAID",      "web",   12000L, 2),
            line("A-02", "TENANT-A", "PAID",      "store", 55000L, 1),
            line("A-03", "TENANT-A", "NEW",       "web",    5000L, 3),
            line("A-04", "TENANT-A", "CANCELLED", "store", 30000L, 1),
            line("A-05", "TENANT-A", "PAID",      "web",    8000L, 2),
            line("A-06", "TENANT-A", "PAID",      "web",    2000L, 5),
            line("A-07", "TENANT-A", "NEW",       "store", 20000L, 1),
            line("B-01", "TENANT-B", "PAID",      "web",   10000L, 4)
        ));
    }

    @Test
    void matchKeepsSixAuthorizedLines() {
        Aggregation matchOnly = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is("TENANT-A")
                    .and("status").in("PAID", "NEW")
            )
        );

        List<Document> rows = template.aggregate(
            matchOnly, "sales_lines", Document.class
        ).getMappedResults();

        assertThat(rows).hasSize(6);
        assertThat(rows)
            .extracting(doc -> doc.getString("_id"))
            .containsExactlyInAnyOrder(
                "A-01", "A-02", "A-03", "A-05", "A-06", "A-07");
        assertThat(rows)
            .extracting(doc -> doc.getString("tenantId"))
            .containsOnly("TENANT-A");
    }

    @Test
    void projectProducesGrossAmountsBeforeGrouping() {
        Aggregation matchAndProject = Aggregation.newAggregation(
            Aggregation.match(
                Criteria.where("tenantId").is("TENANT-A")
                    .and("status").in("PAID", "NEW")
            ),
            Aggregation.project("status")
                .andExpression("unitPriceMinor * quantity")
                .as("grossMinor")
                .andExclude("_id")
        );

        List<Document> rows = template.aggregate(
            matchAndProject, "sales_lines", Document.class
        ).getMappedResults();

        assertThat(rows).hasSize(6);
        assertThat(rows).allSatisfy(row -> {
            assertThat(row).containsKeys("status", "grossMinor");
            assertThat(row).doesNotContainKeys(
                "_id", "unitPriceMinor", "quantity", "tenantId");
        });

        long grandTotal = rows.stream()
            .mapToLong(row -> ((Number) row.get("grossMinor"))
                .longValue())
            .sum();

        assertThat(grandTotal).isEqualTo(140000L);
    }

    @Test
    void completePipelineGroupsAndSortsExactly() {
        var report = new SalesAnalyticsService(template)
            .summarizeTenant("TENANT-A");

        assertThat(report).containsExactly(
            new SalesAnalyticsService.RevenueByStatus(
                "PAID", 4L, 105000L),
            new SalesAnalyticsService.RevenueByStatus(
                "NEW", 2L, 35000L)
        );
    }

    @Test
    void otherTenantCannotChangeAuthorizedTotals() {
        var report = new SalesAnalyticsService(template)
            .summarizeTenant("TENANT-B");

        assertThat(report).containsExactly(
            new SalesAnalyticsService.RevenueByStatus(
                "PAID", 1L, 40000L)
        );
    }
}
```

**Cảnh báo:** `collection.deleteMany(new Document())` xóa toàn bộ `sales_lines` trong database mà bài test đang kết nối. Chỉ chạy khi chắc chắn sử dụng MongoDB test **cô lập** (ví dụ Testcontainers). `@DataMongoTest` không tự chứng minh server là database test an toàn nếu cấu hình môi trường bị sai.

### 13.2. Vì sao kiểm tra từng stage?

- Test `matchKeepsSixAuthorizedLines` bắt lỗi thiếu tenant hoặc sai điều kiện trạng thái.
- Test `projectProducesGrossAmountsBeforeGrouping` bắt lỗi phép nhân hoặc projection làm mất field.
- Test `completePipelineGroupsAndSortsExactly` bắt lỗi khóa nhóm, accumulator và sort.
- Test `otherTenantCannotChangeAuthorizedTotals` kiểm tra phạm vi dữ liệu; B-01 không được cộng vào báo cáo tenant A.

Không chỉ kiểm tra báo cáo có đúng hai hàng. Nếu một dòng PAID bị thiếu và một dòng khác bị cộng hai lần, số hàng nhóm vẫn là hai. Cần assert **giá trị số, ID nguồn, kiểu dữ liệu và cả thứ tự khi thứ tự là hợp đồng API**.

### 13.3. Ma trận kiểm thử bổ sung

| Trường hợp | Mong đợi |
| --- | --- |
| Không có dòng nào khớp `$match` | `$group` theo status không tạo nhóm giả |
| Hai trạng thái có cùng tổng | `$sort` có khóa phụ để thứ tự xác định |
| `unitPriceMinor` hoặc `quantity` thiếu | Có quy tắc validation/null rõ, không âm thầm cộng sai |
| Giá lưu dạng String legacy | Không giả định `$multiply` tự chuyển kiểu |
| Document sai tenant có cùng status | Không xuất hiện trong tổng tenant hiện tại |
| `$project` loại channel | Không thể group tiếp theo channel nếu không giữ field |
| `$unwind` array ba phần tử | Một document có thể tạo ba document tạm |
| `$unwind` trên mảng rỗng/missing | Kiểm tra tác dụng của `preserveNullAndEmptyArrays` |
| `$limit` trước group | Phải phản ánh đúng ý định lấy mẫu, không dùng làm tổng toàn tập |
| Báo cáo giá trị quá lớn | Kiểm tra kiểu số và giới hạn/overflow |

## 14. Trả kết quả qua repository @Aggregation

Ngoài `MongoTemplate`, Spring Data MongoDB hỗ trợ `@Aggregation` trên phương thức repository ở các phiên bản phù hợp. Annotation mô tả **mảng các stage JSON cố định**. Ví dụ gọn để đếm dòng hàng theo trạng thái:

```java
package com.example.shop.sales;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SalesLineRepository
        extends MongoRepository<SalesLine, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': { '$in': ['PAID','NEW'] } } }",
        "{ '$group': { '_id': '$status', 'lineCount': { '$sum': 1 } } }",
        "{ '$sort': { 'lineCount': -1, '_id': 1 } }"
    })
    List<Document> countLinesByStatus(String tenantId);
}
```

Kết quả ở ví dụ trên là PAID với 4 dòng, NEW với 2 dòng; **chưa** tính tổng tiền vì pipeline annotation này chỉ minh họa `$match` → `$group` → `$sort`.

Khi chọn cách viết:

- `@Aggregation` phù hợp khi pipeline **cố định**, đặt cạnh hợp đồng repository và dễ quản lý.
- `MongoTemplate`/Aggregation DSL phù hợp khi cần xây stage động, tái sử dụng khối biểu thức, debug/cấu hình theo nhiều nhánh hoặc thao tác kiểm thử trung gian.
- Cả hai đều chạy **aggregation phía MongoDB**; không có chuyện một cách tự động nhanh hơn khi BSON pipeline tương đương.

Lưu ý về tên annotation: `org.springframework.data.mongodb.repository.Aggregation` là **annotation**, còn `org.springframework.data.mongodb.core.aggregation.Aggregation` là **class xây pipeline Java**. Nếu cùng dùng trong một file, cần import hoặc viết tên đầy đủ để tránh nhầm lẫn.

## 15. Hiệu năng: stage nào tận dụng index và stage nào phải tính?

Pipeline thường chạy trên server MongoDB và giảm lượng dữ liệu phải đưa về Java khi tính tổng theo nhóm. Nhưng **không phải đặt logic vào pipeline thì mặc nhiên nhanh**. Chi phí phụ thuộc số document đi qua từng stage, tính chọn lọc của `$match`, số nhóm, số field phải xử lý và kế hoạch thực thi.

### 15.1. Index cho $match đầu pipeline

Với truy vấn thường xuyên lọc theo tenant và status, một index ứng viên:

```javascript
db.sales_lines.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
)
```

Index này có thể giúp `$match` giảm số document cần đọc khi dữ liệu lớn và filter có tính chọn lọc. Nó **không tự biến `$group` theo tổng tiền thành phép tính dùng index hoàn toàn**; server vẫn cần cộng các dòng phù hợp, tùy kế hoạch.

Nếu báo cáo thường lọc theo thời gian, bổ sung field thời gian/index ghép theo mẫu query thật mới có ý nghĩa. Không nên tạo index chỉ dựa trên tên stage; cần đo với dữ liệu và phân bố tenant đại diện.

### 15.2. Xem explain của aggregation

```javascript
db.sales_lines.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      status: 1,
      grossMinor: {
        $multiply: ["$unitPriceMinor", "$quantity"]
      }
    }
  },
  {
    $group: {
      _id: "$status",
      lineCount: { $sum: 1 },
      totalMinor: { $sum: "$grossMinor" }
    }
  },
  { $sort: { totalMinor: -1, _id: 1 } },
  { $limit: 2 }
])
```

Khi đọc kết quả `explain`, chú ý:

- Stage đọc collection/điều kiện index và số tài liệu được quét.
- `totalKeysExamined`, `totalDocsExamined`, `nReturned` nếu kế hoạch hiển thị các chỉ số tương ứng.
- Các stage sort/group có phải dùng bộ nhớ lớn, spill ra disk hay không (thông tin hiển thị tùy phiên bản).
- Số document đi vào phép tính so với số document cuối cùng trả về.

MongoDB optimizer có thể đẩy một số `$match`/projection hoặc kết hợp các stage khi ngữ nghĩa cho phép. **Pipeline thực thi được tối ưu có thể không hiển thị y hệt thứ tự và cấu trúc khai báo ban đầu**. Đừng coi sự khác biệt giữa explain và JSON gốc là lỗi tự động; hãy xác minh kết quả và thống kê.

### 15.3. $group và $sort có thể là stage “chặn”

`$group` thường phải tích lũy dữ liệu đủ để tính kết quả theo nhóm, còn `$sort` không được index hỗ trợ có thể phải sắp xếp nhiều bản ghi. Chúng có thể tiêu thụ bộ nhớ đáng kể khi:

- Filter đầu vào còn quá rộng.
- Group key có tính phân biệt quá cao, tạo hàng triệu nhóm.
- Mỗi nhóm tích lũy mảng lớn (ví dụ `$push` không giới hạn).
- Sort trên field **mới tính** sau group, không thể trực tiếp tận dụng thứ tự sẵn có của index nguồn.

MongoDB có các quy tắc giới hạn bộ nhớ và tùy chọn cho phép dùng đĩa (`allowDiskUse`), phụ thuộc phiên bản server và cấu hình. Bật dùng đĩa chỉ là **phương án xử lý bộ nhớ**, không tự làm query hiệu quả; hãy ưu tiên tối ưu bộ lọc, schema, index và mức độ gom dữ liệu trước.

### 15.4. Không đưa toàn bộ document vào group nếu không cần

Nếu mục tiêu là cộng tiền, không nên:

```javascript
{
  $group: {
    _id: "$status",
    everyLine: { $push: "$$ROOT" }
  }
}
```

trừ khi nghiệp vụ **thật sự** cần toàn bộ document của từng dòng trong kết quả. `$push: "$$ROOT"` có thể tạo mảng rất lớn, tốn RAM và dữ liệu truyền về. Với báo cáo tổng, dùng `$sum`, `$avg`, `$min`, `$max` và các accumulator thích hợp sẽ rõ ràng và tiết kiệm hơn.

## 16. Đọc kết quả lớn, streaming và reactive access

`AggregationResults<Document>.getMappedResults()` phù hợp khi kết quả báo cáo nhỏ như hai nhóm. Nhưng nếu pipeline trả rất nhiều document, gom tất cả vào một `List` ở Java có thể làm tăng bộ nhớ ứng dụng.

### 16.1. aggregateStream với MongoTemplate

Spring Data MongoDB cung cấp đường đọc aggregation dạng stream ở các phiên bản phù hợp:

```java
import java.util.stream.Stream;
import org.bson.Document;

try (Stream<Document> stream = template.aggregateStream(
        pipeline, "sales_lines", Document.class)) {
    stream.forEach(doc -> {
        // Xử lý từng document kết quả.
        System.out.println(doc.toJson());
    });
}
```

Đây là đoạn mã trong một method/class đã có `MongoTemplate template` và `Aggregation pipeline`. Đóng stream bằng `try-with-resources` để giải phóng cursor/tài nguyên; không mở rồi giữ qua request HTTP không giới hạn. Việc đọc stream **không làm stage `$group` phải tính trên ít dữ liệu hơn**, nó chủ yếu tránh giữ toàn bộ kết quả ở phía Java.

### 16.2. ReactiveMongoTemplate

Trong ứng dụng reactive:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import reactor.core.publisher.Flux;

public Flux<Document> aggregateReactive(
        ReactiveMongoTemplate template,
        Aggregation pipeline) {

    return template.aggregate(
        pipeline, "sales_lines", Document.class);
}
```

Publisher `Flux<Document>` phát các document kết quả khi có subscriber, nhưng **ngữ nghĩa `$match`/`$project`/`$group` không đổi**. Nếu ứng dụng xử lý lượng lớn kết quả, vẫn cần backpressure, timeout, giới hạn bộ nhớ/khối lượng output và chính sách đóng/ngắt pipeline khi client hủy.

**Không trộn blocking `MongoTemplate` vào reactive event loop** rồi kỳ vọng nó tự thành non-blocking. Chọn reactive driver/template và cách xử lý phù hợp từ đầu.

### 16.3. Aggregation đọc và aggregation ghi

Các pipeline trong bài chỉ lọc, biến đổi và trả kết quả. MongoDB còn có các stage chuyên dụng như `$out` và `$merge` dùng để **ghi kết quả aggregation vào collection**. Đừng thêm những stage đó vào pipeline báo cáo chỉ đọc khi chưa chủ đích:

| Pipeline kết thúc bằng | Ý nghĩa |
| --- | --- |
| `$project` / `$group` / `$sort` / `$limit` | Trả document kết quả, không tự ghi collection nguồn |
| `$out` hoặc `$merge` | Có thể ghi kết quả sang collection; cần quyền, thiết kế và kiểm thử riêng |

Nếu cần ghi dữ liệu tổng hợp thành collection vật lý, đó là một bài toán *materialized view* với ràng buộc cập nhật/nhất quán, không chỉ là thay đổi cách hiển thị báo cáo.

## 17. Những lỗi thường gặp khi xây pipeline

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Báo cáo tenant A có cả doanh thu tenant B | `$match` thiếu tenant hoặc nhóm OR đặt sai phạm vi | Đặt tenant ở điều kiện AND bắt buộc và test dữ liệu tenant khác |
| Một stage sau `$project` không tìm thấy field | Field nguồn đã bị loại ở bước project | Giữ field cần dùng hoặc chuyển stage lên trước |
| Output group không có status như entity nguồn | `$group` thay schema, khóa nằm trong `_id` | Dùng DTO riêng hoặc `$project` đổi tên `_id` |
| Đếm ra số dòng thay vì số đơn | Mỗi document nguồn là một line item | Dùng đúng tên `lineCount` hoặc group distinct theo orderId |
| Tổng nhỏ bất thường | `$limit` đặt trước `$group` hoặc filter loại quá nhiều | Kiểm tra cardinality sau từng stage |
| Tổng bị cộng lặp | `$unwind` làm một document thành nhiều document | Xác định đúng cấp đếm; cân nhắc group lại theo ID trước |
| Số tiền sai dù count đúng | Kiểu BSON lẫn String/Number/null; công thức sai | Kiểm tra `$type`, validation và migration |
| `$sort` không làm đúng ý định | Sort trên field đã mất, hoặc sort trước group | Sort theo field tồn tại sau stage thích hợp |
| Kết quả group thay đổi thứ tự ngẫu nhiên | Thiếu `$sort` sau `$group` | Bổ sung sort và khóa phụ |
| Query chậm dù output chỉ có 2 nhóm | Group/sort phải xử lý rất nhiều dòng | `$match` sớm, index phù hợp, xem explain và độ chọn lọc |
| Aggregation trả field null vào Java primitive | Schema output không khớp DTO/entity | Dùng read model phù hợp, validate dữ liệu và mapping |
| Gắn `$set` trong aggregation nhưng không thấy DB đổi | `$set` ở đây là stage biến đổi kết quả, không phải update command | Dùng update API nếu ý định là ghi |
| Báo cáo lớn làm tăng heap Java | `getMappedResults()` gom nhiều hàng vào List | Giới hạn/stream kết quả, kiểm soát tài nguyên |
| Đọc dữ liệu từ nhiều collection nhưng chưa thấy kết quả join | Chưa dùng `$lookup`/`$unwind` đúng cách | Thiết kế pipeline join/array cardinality riêng |

## 18. Checklist thiết kế một aggregation đúng

1. **Nguồn dữ liệu là gì?** Một document biểu diễn đơn hàng, dòng hàng hay sự kiện? Mỗi document tương ứng một đơn vị đếm nào?
2. **Phạm vi quyền là gì?** `tenantId`/storeId phải được xác minh và đặt vào pipeline.
3. **Đầu vào mỗi stage có schema gì?** Liệt kê các field hiện có, đặc biệt sau `$project` và `$group`.
4. **Stage này ảnh hưởng số document ra sao?** Giữ số lượng, lọc bớt, nhân bản qua unwind hay gom nhóm?
5. **Expression dùng field nào?** Field có tồn tại/đúng kiểu BSON không? Cần `$ifNull` hay validation không?
6. **Accumulator có đúng ý định không?** `$sum: 1` đang đếm dòng hay đếm entity nghiệp vụ duy nhất?
7. **Thứ tự stage có đúng không?** Filter gốc sớm, tính field trước khi sử dụng, group trước khi sort theo tổng.
8. **Đầu ra có schema gì?** `_id` là ID nguồn hay group key? Java nên dùng DTO nào?
9. **Có cần giới hạn hoặc stream output?** Tránh trả mảng báo cáo vô hạn về client.
10. **Có kiểm thử từng tiền tố pipeline và BSON raw không?** Đừng chỉ mock kết quả cuối.
11. **Có index và đo plan thật chưa?** Đo `explain`, thời gian, bộ nhớ và độ trễ ở dữ liệu đại diện.
12. **Pipeline có side effect không?** Với `$out`/`$merge`, phải xác định rõ collection ghi đích và quyền thao tác.

## 19. Bài tập vận dụng

Một hệ thống giao hàng lưu collection `deliveries`:

```javascript
{
  _id: "DEL-001",
  tenantId: "TENANT-X",
  state: "DELIVERED",
  zone: "HCM",
  feeMinor: NumberLong(20000),
  packageCount: 2,
  labels: ["fragile", "priority"]
}
```

Mục tiêu: thống kê doanh thu phí giao hàng theo `zone`, trong phạm vi một tenant, chỉ tính `state=DELIVERED`. Phí thực tế cho mỗi document được quy định ở bài tập là `feeMinor * packageCount` (chỉ là quy ước mô phỏng, cần đối chiếu nghiệp vụ thật).

Hãy thực hiện:

1. Viết `$match` giới hạn tenant và state. Cho biết nếu thiếu tenant, dữ liệu nào có thể bị cộng nhầm.
2. Viết `$project` tạo `grossFeeMinor` bằng `$multiply` và giữ `zone`.
3. Viết `$group` theo zone, tính `deliveryCount` và `totalFeeMinor`.
4. Sắp xếp tổng tiền giảm dần, thêm khóa phụ để có thứ tự quyết định, giới hạn 5 zone.
5. Thử đưa `$limit: 5` **trước** group và giải thích vì sao ngữ nghĩa báo cáo thay đổi.
6. Sửa pipeline để thống kê theo cặp `zone + state`; dự đoán hình dạng `_id` của mỗi nhóm.
7. Đưa `$unwind: "$labels"` trước group, sau đó giải thích vì sao `deliveryCount` có thể bị tăng giả tạo nếu một delivery có nhiều labels.
8. Chuyển pipeline sang Java bằng `Aggregation.newAggregation(...)` và `MongoTemplate.aggregate(...)`.
9. Viết integration test có document của tenant khác, zone trùng nhau và một document thiếu `feeMinor`.
10. Đề xuất index cho `$match`, dùng `explain("executionStats")` và so sánh tốc độ khi có/không có index trên dữ liệu đủ lớn.

**Gợi ý lời giải pipeline:**

```javascript
db.deliveries.aggregate([
  {
    $match: {
      tenantId: "TENANT-X",
      state: "DELIVERED"
    }
  },
  {
    $project: {
      zone: 1,
      grossFeeMinor: {
        $multiply: ["$feeMinor", "$packageCount"]
      }
    }
  },
  {
    $group: {
      _id: "$zone",
      deliveryCount: { $sum: 1 },
      totalFeeMinor: { $sum: "$grossFeeMinor" }
    }
  },
  { $sort: { totalFeeMinor: -1, _id: 1 } },
  { $limit: 5 }
])
```

Nếu `feeMinor` hoặc `packageCount` thiếu, hãy quyết định rõ: **loại document không hợp lệ**, **thất bại kiểm thử**, hay dùng một quy tắc fallback được nghiệp vụ chấp nhận. Đừng mặc định mọi giá trị thiếu đều bằng 0 rồi gọi đó là doanh thu hợp lệ.

## 20. Tài liệu tham khảo

- Spring Data MongoDB — [Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): `Aggregation`, `AggregationOperation`, SpEL expression và kết quả aggregation.
- Spring Data MongoDB — [Aggregation API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/Aggregation.html): builders `match`, `project`, `group`, `sort`, `limit`.
- Spring Data MongoDB — [Aggregation Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): annotation `@Aggregation`.
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): định nghĩa pipeline và luồng document.
- MongoDB Manual — [Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation-pipeline/): danh mục stage và đặc điểm đầu ra.
- MongoDB Manual — [Aggregation Expressions](https://www.mongodb.com/docs/manual/reference/operator/aggregation/): toán tử expression, điều kiện và số học.
- MongoDB Manual — [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): tối ưu, đẩy filter và xử lý stage.
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): cách đọc kế hoạch và chi phí thực thi.

## Ghi nhớ

**Pipeline** là chuỗi stage; **stage** nhận document từ bước trước và có thể lọc, đổi schema, nhân bản, gom nhóm hoặc sắp xếp; **expression** là phép tính trên field trong từng stage. Trong ví dụ, 8 document nguồn → `$match` còn 6 → `$project` tính `grossMinor` nhưng vẫn 6 → `$group` còn 2 nhóm → `$sort` và `$limit` quyết định thứ tự/độ dài kết quả. Sau `$group`, `_id` là **khóa nhóm**, không còn là ID document nguồn. Viết pipeline đúng nghĩa bắt đầu từ việc hiểu **mỗi stage nhận gì và phát ra gì**, rồi mới chuyển sang `Aggregation`/`MongoTemplate`, kiểm thử BSON thực và tối ưu theo `explain`.
