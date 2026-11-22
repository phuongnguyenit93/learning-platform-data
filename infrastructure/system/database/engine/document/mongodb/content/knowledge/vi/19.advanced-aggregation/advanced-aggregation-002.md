# Tác động của index, số bản ghi khớp và kích thước kết quả khi join trong MongoDB

Trong MongoDB, `$lookup` cho phép một pipeline aggregation lấy dữ liệu từ collection khác và gắn kết quả vào document đang xử lý. Đây là công cụ hữu ích để hiển thị khách hàng kèm đơn hàng, sản phẩm kèm tồn kho, nhân viên kèm phòng ban, hoặc báo cáo dựa trên nhiều loại dữ liệu. Tuy nhiên, một pipeline `$lookup` đúng cú pháp vẫn có thể **rất chậm, tiêu tốn bộ nhớ, trả document quá lớn hoặc ghép sai dữ liệu** nếu không đánh giá ba yếu tố cốt lõi:

1. **Index trên collection được tra cứu (foreign collection):** có giúp tìm nhanh bản ghi tương ứng với mỗi document đầu vào không?
2. **Số document đầu vào và số bản ghi khớp của từng document:** một khách hàng có 2 đơn khác hoàn toàn với một khách hàng có 200.000 đơn.
3. **Kích thước dữ liệu sau join:** `$lookup` tạo mảng kết quả, còn `$unwind` có thể nhân số document của pipeline; cả hai đều ảnh hưởng CPU, I/O, RAM, mạng và giới hạn kích thước BSON.

Bài thuộc chương **Aggregation nâng cao** của module *Database Engine Document MongoDB*. Trọng tâm là hiểu hiệu năng join trong MongoDB một cách định lượng, từ mô hình chi phí, index và độ chọn lọc đến cardinality, output size, `explain`, và thiết kế pipeline an toàn khi tải tăng. Ví dụ chạy bằng **mongosh** trong database lab `lookup_performance_lab`. Một số cách tối ưu và hình dạng `explain` phụ thuộc phiên bản MongoDB, execution engine, cách shard dữ liệu và loại index; phải đo trong deployment thực tế trước khi suy ra hành vi production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **left outer join** của `$lookup` với join làm tăng số dòng sau `$unwind`.
- Viết `$lookup` dạng `localField/foreignField` và dạng có `pipeline`, `let`, `$expr`.
- Giải thích tại sao index trên **foreignField** thường quan trọng hơn việc chỉ index localField.
- Đếm số document đầu vào, số match mỗi document, tổng số kết quả ghép và **fan-out**.
- Nhận biết cách một hoặc hai document có số match cực lớn có thể gây **cardinality explosion** và document lớn.
- Phân biệt giới hạn **16 MiB cho BSON document** với giới hạn bộ nhớ của một số stage aggregation.
- Lựa chọn đúng vị trí `$match`, `$project`, `$sort`, `$limit` và `$unwind` để giảm tài nguyên mà vẫn giữ ngữ nghĩa.
- Đọc các chỉ số index/scan trong `explain("executionStats")`, có lưu ý về kế hoạch `EQ_LOOKUP` và các field thống kê phụ thuộc phiên bản.
- Thiết kế join có **tenant isolation**, đúng kiểu khóa và bảo đảm không lọt dữ liệu từ tenant khác.
- Quyết định khi nào nên dùng `$lookup`, khi nào nên pre-aggregate, materialize, nhúng dữ liệu hoặc thay đổi data model.

## 2. `$lookup` tạo ra kết quả như thế nào?

### 2.1. Dạng equality join cơ bản

Giả sử có hai collection:

~~~javascript
// customers
{ _id: "c-01", customerCode: "U100", name: "An" }

// orders
{ _id: "o-101", customerCode: "U100", amount: 100 }
{ _id: "o-102", customerCode: "U100", amount: 250 }
~~~

Pipeline:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  }
])
~~~

Một document customer được gắn mảng những order phù hợp:

~~~javascript
{
  _id: "c-01",
  customerCode: "U100",
  name: "An",
  orders: [
    { _id: "o-101", customerCode: "U100", amount: 100 },
    { _id: "o-102", customerCode: "U100", amount: 250 }
  ]
}
~~~

Đây là join kiểu **left outer join**: nếu customer không có order, customer vẫn ở kết quả, với mảng `orders: []`. `$lookup` **không** tự biến một customer có 100 orders thành 100 document độc lập. Nó trả về **một customer document với một mảng 100 phần tử**.

### 2.2. `$unwind` mới làm tăng số dòng

Khi tiếp tục:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  { $unwind: "$orders" }
])
~~~

thì một customer có hai orders tạo **hai document pipeline**, mỗi document mang một order. Customer không có order sẽ bị loại nếu không dùng `preserveNullAndEmptyArrays`.

~~~mermaid
flowchart LR
    A["1 customer"] --> L["$lookup"]
    L --> B["1 document + mảng 3 orders"]
    B --> U["$unwind"]
    U --> C["3 document đầu ra"]
~~~

Đây là khác biệt quan trọng khi tính kích thước:

| Bước | Số document | Kích thước mỗi document |
|---|---:|---|
| Trước join | Một document/customer | Chỉ field customer |
| Sau `$lookup` | Vẫn một document/customer | **Tăng theo tổng kích thước orders gắn vào** |
| Sau `$unwind` | Một document cho mỗi order khớp | Thường nhỏ hơn mỗi document có mảng lớn, nhưng lặp field customer nhiều lần |

**Không đồng nhất “số document sau `$lookup`” với “số phần tử trong các mảng đã join”.** Hai chỉ số này cùng cần được đo.

## 3. Mô hình chi phí: input × số match × kích thước dữ liệu

Đặt:

- `N`: số document **đi vào `$lookup`** sau các stage trước.
- `m_i`: số foreign document khớp với document đầu vào thứ `i`.
- `M = m_1 + m_2 + ... + m_N`: tổng số phần tử join được.
- `S_i`: số byte cần lưu/serialize của phần tử foreign thứ `i` sau projection.
- `B`: kích thước các field local và overhead khác.

Ta có:

~~~text
Số document sau $lookup:           N
Tổng số phần tử foreign đã ghép:   M = Σ m_i

Số document sau $unwind mặc định:  M
Số document sau $unwind preserve:  M + số local document có m_i = 0

Kích thước document sau $lookup:
  xấp xỉ kích thước local + tổng kích thước phần tử matched + overhead mảng/BSON
~~~

Nếu trung bình mỗi customer có 20 orders, với 10.000 customers:

~~~text
N = 10.000 customers
Avg matches = 20 orders/customer
M ≈ 200.000 matched orders
~~~

Khi `$unwind`, pipeline có thể biến 10.000 documents thành 200.000 documents. Nếu một order sau projection có khoảng 1 KiB, chỉ riêng payload foreign ở mức khái niệm đã là khoảng **200 MiB** dữ liệu được đọc/gắn vào những document trung gian, chưa kể field local, BSON overhead, index work và các stage tiếp theo.

**Đây chỉ là ước lượng thiết kế, không phải công thức thời gian chạy.** Hiệu năng thực còn phụ thuộc index, cache, mức trùng key, phân phối dữ liệu, số shard, sort, projection và lượng dữ liệu được truyền giữa server/client.

### 3.1. Phân phối lệch quan trọng hơn trung bình

Nếu 9.999 customers có mỗi người một order, nhưng một customer có 250.000 orders, trung bình toàn tập vẫn che giấu **một local document cực lớn**. Dù số match trung bình nhỏ, document của customer bất thường có thể đụng giới hạn BSON 16 MiB khi `$lookup` gắn cả 250.000 orders vào một mảng.

Khi đánh giá cardinality, cần nhìn:

- Số foreign match trung bình.
- **P95/P99/max matches trên mỗi local key**.
- Kích thước trung bình/P95 của một foreign document.
- Kích thước local document trước join.
- Số document còn lại sau `$match`.

Không chỉ đo tổng M, mà còn đo **max m_i**.

## 4. Chuẩn bị dữ liệu lab có cardinality và tenant trùng khóa

Chọn database lab:

~~~javascript
use lookup_performance_lab
~~~

Hai collection minh họa:

- `customers`: một document cho mỗi customer; `customerCode` chỉ duy nhất **trong tenant**, không duy nhất toàn hệ thống.
- `orders`: nhiều order cho một customer; có cả order không có customer tương ứng.

### 4.1. Tạo customers

~~~javascript
db.customers.insertMany([
  {
    _id: "c-01", tenantId: "t-01",
    customerCode: "U100", name: "An", segment: "VIP"
  },
  {
    _id: "c-02", tenantId: "t-01",
    customerCode: "U200", name: "Bình", segment: "REGULAR"
  },
  {
    _id: "c-03", tenantId: "t-01",
    customerCode: "U300", name: "Chi", segment: "VIP"
  },
  {
    _id: "c-04", tenantId: "t-02",
    customerCode: "U100", name: "Dung", segment: "REGULAR"
  },
  {
    _id: "c-05", tenantId: "t-02",
    customerCode: "U400", name: "Hà", segment: "VIP"
  },
  {
    _id: "c-06", tenantId: "t-01",
    customerCode: "U999", name: "Lan", segment: "REGULAR"
  }
])
~~~

`c-01` của tenant `t-01` và `c-04` của tenant `t-02` **có cùng `customerCode = "U100"`**. Đây là dữ liệu hợp lệ nếu mã chỉ cần duy nhất theo tenant, nhưng sẽ gây **cross-tenant join** nếu filter chỉ dựa vào customerCode.

### 4.2. Tạo orders

~~~javascript
db.orders.insertMany([
  {
    _id: "o-101", tenantId: "t-01", customerCode: "U100",
    status: "PAID", amount: NumberDecimal("100"),
    createdAt: ISODate("2026-09-01T08:00:00Z"),
    payload: { note: "Đơn đầu của An", channel: "WEB" }
  },
  {
    _id: "o-102", tenantId: "t-01", customerCode: "U100",
    status: "PAID", amount: NumberDecimal("250"),
    createdAt: ISODate("2026-09-03T08:00:00Z"),
    payload: { note: "Đơn thứ hai của An", channel: "APP" }
  },
  {
    _id: "o-103", tenantId: "t-01", customerCode: "U100",
    status: "REFUNDED", amount: NumberDecimal("80"),
    createdAt: ISODate("2026-09-04T08:00:00Z"),
    payload: { note: "Đơn hoàn tiền", channel: "WEB" }
  },
  {
    _id: "o-104", tenantId: "t-01", customerCode: "U200",
    status: "PAID", amount: NumberDecimal("400"),
    createdAt: ISODate("2026-09-02T08:00:00Z"),
    payload: { note: "Đơn của Bình", channel: "APP" }
  },
  {
    _id: "o-105", tenantId: "t-01", customerCode: "U200",
    status: "CREATED", amount: NumberDecimal("100"),
    createdAt: ISODate("2026-09-05T08:00:00Z"),
    payload: { note: "Đơn chưa thanh toán", channel: "WEB" }
  },
  {
    _id: "o-106", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("100"),
    createdAt: ISODate("2026-09-01T09:00:00Z"),
    payload: { note: "Chi 1", channel: "WEB" }
  },
  {
    _id: "o-107", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("110"),
    createdAt: ISODate("2026-09-02T09:00:00Z"),
    payload: { note: "Chi 2", channel: "APP" }
  },
  {
    _id: "o-108", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("120"),
    createdAt: ISODate("2026-09-03T09:00:00Z"),
    payload: { note: "Chi 3", channel: "APP" }
  },
  {
    _id: "o-109", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("130"),
    createdAt: ISODate("2026-09-04T09:00:00Z"),
    payload: { note: "Chi 4", channel: "WEB" }
  },
  {
    _id: "o-110", tenantId: "t-01", customerCode: "U300",
    status: "CREATED", amount: NumberDecimal("140"),
    createdAt: ISODate("2026-09-05T09:00:00Z"),
    payload: { note: "Chi 5", channel: "WEB" }
  },
  {
    _id: "o-111", tenantId: "t-01", customerCode: "U300",
    status: "PAID", amount: NumberDecimal("150"),
    createdAt: ISODate("2026-09-06T09:00:00Z"),
    payload: { note: "Chi 6", channel: "APP" }
  },
  {
    _id: "o-112", tenantId: "t-02", customerCode: "U100",
    status: "PAID", amount: NumberDecimal("200"),
    createdAt: ISODate("2026-09-03T10:00:00Z"),
    payload: { note: "Dung 1", channel: "APP" }
  },
  {
    _id: "o-113", tenantId: "t-02", customerCode: "U100",
    status: "CANCELLED", amount: NumberDecimal("300"),
    createdAt: ISODate("2026-09-05T10:00:00Z"),
    payload: { note: "Dung 2", channel: "WEB" }
  },
  {
    _id: "o-114", tenantId: "t-02", customerCode: "U400",
    status: "PAID", amount: NumberDecimal("200"),
    createdAt: ISODate("2026-09-01T11:00:00Z"),
    payload: { note: "Hà 1", channel: "WEB" }
  },
  {
    _id: "o-115", tenantId: "t-02", customerCode: "U400",
    status: "CREATED", amount: NumberDecimal("210"),
    createdAt: ISODate("2026-09-02T11:00:00Z"),
    payload: { note: "Hà 2", channel: "APP" }
  },
  {
    _id: "o-116", tenantId: "t-02", customerCode: "U400",
    status: "PAID", amount: NumberDecimal("220"),
    createdAt: ISODate("2026-09-04T11:00:00Z"),
    payload: { note: "Hà 3", channel: "WEB" }
  },
  {
    _id: "o-117", tenantId: "t-02", customerCode: "U400",
    status: "PAID", amount: NumberDecimal("230"),
    createdAt: ISODate("2026-09-06T11:00:00Z"),
    payload: { note: "Hà 4", channel: "APP" }
  },
  {
    _id: "o-118", tenantId: "t-01", customerCode: "U500",
    status: "PAID", amount: NumberDecimal("999"),
    createdAt: ISODate("2026-09-07T11:00:00Z"),
    payload: { note: "Order chưa có customer", channel: "WEB" }
  }
])
~~~

Các lệnh insert chỉ dùng trên **database lab rỗng**. Chạy lại với cùng `_id` sẽ tạo lỗi duplicate key; không xóa dữ liệu ngoài phạm vi bài để thử lại. Xem số lượng:

~~~javascript
db.customers.countDocuments({}) // 6
db.orders.countDocuments({})    // 18
~~~

### 4.3. Bảng phân phối số order đúng theo tenant

| Customer | Tenant | Mã | Số order đúng | Ghi chú |
|---|---|---|---:|---|
| `c-01` | `t-01` | `U100` | 3 | Cùng customerCode với `c-04` nhưng khác tenant |
| `c-02` | `t-01` | `U200` | 2 | Có PAID và CREATED |
| `c-03` | `t-01` | `U300` | 6 | Nhiều match nhất trong lab |
| `c-04` | `t-02` | `U100` | 2 | Khóa trùng xuyên tenant |
| `c-05` | `t-02` | `U400` | 4 | Có ba PAID |
| `c-06` | `t-01` | `U999` | 0 | Không có order |
| **Tổng** | | | **17** | Một order `o-118` không có customer |

Đây sẽ là baseline kiểm chứng **cardinality và tính đúng đắn** của pipeline. Tổng foreign matches hợp lệ là **17**, không phải 18, vì `o-118` không có customer tương ứng. Tổng có thể lớn hơn 18 nếu join sai khóa và một order bị gắn vào nhiều customer — đó là lỗi cần nhận biết.

## 5. Join đơn giản: đúng cú pháp nhưng có thể sai tenant

Chạy:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      matchCount: { $size: "$orders" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Kết quả về số match:

| Customer | `matchCount` khi chỉ join `customerCode` | Số đúng |
|---|---:|---:|
| `c-01` (t-01/U100) | 5 | 3 |
| `c-02` (t-01/U200) | 2 | 2 |
| `c-03` (t-01/U300) | 6 | 6 |
| `c-04` (t-02/U100) | 5 | 2 |
| `c-05` (t-02/U400) | 4 | 4 |
| `c-06` (t-01/U999) | 0 | 0 |
| **Tổng** | **22** | **17** |

**Vấn đề:** `U100` xuất hiện ở cả t-01 lẫn t-02. `c-01` nhận thêm hai đơn của `c-04`, và `c-04` nhận thêm ba đơn của `c-01`. Join này không chỉ chậm hơn mà còn **sai nghiệp vụ, có thể gây lộ dữ liệu xuyên tenant**.

### Tác động kép của khóa join không đủ đặc hiệu

Sai điều kiện join dẫn tới hai hậu quả đồng thời:

1. **Correctness/security:** gắn dữ liệu của tenant khác vào document.
2. **Performance:** số match tăng từ 17 lên 22, làm đọc nhiều foreign docs hơn, tăng kích thước mảng và có thể khuếch đại sau `$unwind`.

Tối ưu hiệu năng không được tách rời việc **thiết kế khóa join đúng**. Một index hoàn hảo trên `customerCode` vẫn không làm dữ liệu cross-tenant trở nên hợp lệ.

## 6. Join đúng tenant bằng `pipeline` và `let`

Khi join cần nhiều điều kiện, có thể dùng `$lookup` với pipeline phụ (*foreign pipeline*) và biến `let`.

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: {
        cCode: "$customerCode",
        cTenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$customerCode", "$$cCode"] },
                { $eq: ["$tenantId", "$$cTenant"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      matchCount: { $size: "$orders" }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

`let` lấy các giá trị từ từng customer local; `$$cCode` và `$$cTenant` là biến bên trong foreign pipeline. `$expr` cho phép so sánh field ở collection `orders` với biến đó.

Kết quả `matchCount` là:

~~~text
c-01 -> 3
c-02 -> 2
c-03 -> 6
c-04 -> 2
c-05 -> 4
c-06 -> 0
Tổng -> 17
~~~

### 6.1. Dạng kết hợp equality join và pipeline bổ sung

Trên những phiên bản MongoDB hỗ trợ cú pháp kết hợp `localField/foreignField` với `pipeline`, có thể dùng equality join rõ ràng cho `customerCode` và thêm điều kiện tenant:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      let: {
        cTenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: ["$tenantId", "$$cTenant"]
            }
          }
        },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "orders"
    }
  }
])
~~~

Đây là cách thể hiện một khóa equality cố định kèm điều kiện phụ. Tuy nhiên, khả năng sử dụng **compound index cho cả hai điều kiện** cần được xác nhận bằng `explain`; không mặc định mọi biểu thức `$expr` đều được optimizer chuyển thành index bounds hiệu quả.

### 6.2. Vì sao không chỉ `$match` theo tenant bên ngoài?

Pipeline sau **không sửa được join sai**:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  }
])
~~~

`$match` đầu chỉ lọc **customers** của t-01, không tự áp đặt `tenantId = "t-01"` trên **orders** được join. `c-01` vẫn có thể nhận đơn U100 từ t-02. Cần áp ràng buộc tenant **trong điều kiện join**.

## 7. Index trên foreign collection: yếu tố ảnh hưởng lớn nhất

Với join equality:

~~~javascript
{
  $lookup: {
    from: "orders",
    localField: "customerCode",
    foreignField: "customerCode",
    as: "orders"
  }
}
~~~

field cần được tra cứu cho từng customer là **`orders.customerCode`**, thuộc collection `orders`. Index trên foreign side thường quyết định query có thể định vị nhanh các order tương ứng hay phải xem lượng document lớn.

### 7.1. Index foreignField cơ bản

~~~javascript
db.orders.createIndex(
  { customerCode: 1 },
  { name: "idx_orders_customer_code" }
)
~~~

Khi `$lookup` xử lý customer `U300`, index có thể giúp tìm vùng keys của order U300 thay vì scan toàn bộ orders. Trên tập dữ liệu lớn và nhiều local documents, sự khác biệt có thể rất đáng kể.

**Lưu ý:** index này giúp thực thi join, **không sửa việc mã U100 bị trùng giữa hai tenant**. Join vẫn phải bổ sung tenant để đúng nghiệp vụ.

### 7.2. Compound index cho điều kiện nhiều field

Đối với join theo `tenantId + customerCode`:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1
  },
  { name: "idx_orders_tenant_customer" }
)
~~~

Hoặc nếu các query còn sort theo ngày trong phạm vi customer:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_orders_tenant_customer_date" }
)
~~~

Hai field đầu có thể phục vụ equality theo tenant/customer; hai field sau có thể phục vụ lấy order mới nhất cho customer trong trường hợp planner sử dụng được điều kiện và thứ tự tương ứng.

Chọn thứ tự key index theo **những query thực sự chạy**. Nếu rất nhiều query chỉ lọc `customerCode` trên toàn hệ thống, index bắt đầu bằng tenant không có prefix tốt cho chúng. Nếu hầu hết query bắt buộc scope tenant, để tenant ở đầu thường là ứng viên hợp lý. Không tạo tất cả index ứng viên chỉ vì muốn “đủ bộ”: mỗi index tăng chi phí insert/update/delete.

### 7.3. Index ở local collection có giúp join không?

~~~javascript
db.customers.createIndex(
  { tenantId: 1, segment: 1 },
  { name: "idx_customers_tenant_segment" }
)
~~~

Index này có thể hỗ trợ **lọc local documents**:

~~~javascript
{ $match: { tenantId: "t-01", segment: "VIP" } }
~~~

qua đó giảm số customer phải đưa vào `$lookup`. Nó không thay thế index trên **`orders.customerCode/tenantId`** phục vụ tìm foreign matches.

Phân biệt:

| Index | Tác dụng tiềm năng |
|---|---|
| `customers.{tenantId, segment}` | Giảm số local document trước join |
| `orders.{customerCode}` | Hỗ trợ equality lookup theo customerCode |
| `orders.{tenantId, customerCode}` | Hỗ trợ join đúng tenant khi query shape/indexability phù hợp |
| `orders.{tenantId, customerCode, createdAt}` | Hỗ trợ join có thêm sort/top-N theo ngày trong tình huống phù hợp |

**Quy tắc thực hành:** xác định collection nào đang được đọc ở mỗi stage; đừng nhìn tên `localField` rồi tạo index ở local và cho rằng đã tối ưu foreign lookup.

## 8. `$expr` trong correlated lookup và khả năng dùng index

Một câu hỏi quan trọng: “Có index trên foreign field thì `$lookup` dạng `pipeline` có dùng được không?”

**Không có câu trả lời luôn luôn.** MongoDB có thể dùng index cho một số biểu thức so sánh trong foreign pipeline `$match` với `$expr`, nhưng phải tuân theo điều kiện của phiên bản và query shape.

Ví dụ:

~~~javascript
{
  $match: {
    $expr: {
      $eq: ["$customerCode", "$$cCode"]
    }
  }
}
~~~

`$eq` giữa **field foreign** và **giá trị biến `let`** có thể được xem xét sử dụng index nếu giá trị biến được xác định thành một hằng số cho lượt lookup đó và các điều kiện khác phù hợp. Các toán tử so sánh như `$eq`, `$lt`, `$lte`, `$gt`, `$gte` có những trường hợp được phép dùng index trong `$expr`.

### 8.1. Giới hạn cần nhớ

- So sánh **field với hằng số** có cơ hội dùng index; **field với field** thường không có cùng khả năng indexability.
- Nếu biến `let` phân giải thành **missing/empty value** ở một lượt join, khả năng dùng index có thể bị hạn chế.
- Một số quy tắc của `$expr` trong `$lookup` không dùng được **multikey index**, cũng như có giới hạn với **sparse/partial index** theo tài liệu của phiên bản.
- Biểu thức tính toán lên foreign field như `$toString`, `$concat` hoặc chuyển kiểu tùy ý có thể ngăn dùng range/index bounds như so sánh field trực tiếp.
- Các stage khác trong foreign pipeline có thể ảnh hưởng việc đẩy filter và dùng sort index.

Không viết:

~~~javascript
// Có thể rất tốn kém vì tính toán trên foreign field trong điều kiện.
{
  $match: {
    $expr: {
      $eq: [
        { $toString: "$customerCode" },
        "$$cCode"
      ]
    }
  }
}
~~~

nếu bạn có thể lưu `customerCode` nhất quán kiểu string và so sánh trực tiếp. Đừng dùng convert trong query để sửa một schema lâu dài có kiểu sai; chuẩn hóa tại thời điểm ghi và migrate dữ liệu là phương án bền vững hơn.

### 8.2. Vì sao cần xem `explain`?

Cùng một index có thể được dùng rất khác giữa:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  customerCode: "U300"
})
~~~

và:

~~~javascript
{
  $lookup: {
    from: "orders",
    let: { tenant: "$tenantId", code: "$customerCode" },
    pipeline: [
      {
        $match: {
          $expr: {
            $and: [
              { $eq: ["$tenantId", "$$tenant"] },
              { $eq: ["$customerCode", "$$code"] }
            ]
          }
        }
      }
    ],
    as: "orders"
  }
}
~~~

Query `find()` riêng là phép tham chiếu tốt để biết index có phù hợp với equality trên hai field không, **nhưng không chứng minh** nested `$lookup` sẽ dùng index giống hệt. Cần kiểm tra chính pipeline join trong `explain("executionStats")`.

## 9. Số local documents: lọc trước join có thể giảm chi phí rất mạnh

Giả sử collection có:

~~~text
1.000.000 customers
30.000.000 orders
~~~

API chỉ cần những khách VIP của tenant t-01, ví dụ 800 customers. Nếu join trước rồi mới lọc:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  { $match: { tenantId: "t-01", segment: "VIP" } }
])
~~~

thì về mặt **luồng logic**, `$lookup` đang đứng trước filter local. Nếu engine không thể đẩy filter sớm qua các stage một cách an toàn, nó có thể phải thực hiện nhiều lượt lookup không cần thiết. Đừng dựa vào optimizer “tự sửa hết mọi thứ”.

### 9.1. Đưa filter local lên trước

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01", segment: "VIP" } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  }
])
~~~

Lúc này có thể chỉ còn 800 local documents cần join, thay vì 1 triệu. Index `customers.{tenantId,segment}` có thể giúp lọc 800 documents, và index trên `orders` phục vụ từng lookup tương ứng.

### 9.2. Lab: giảm local input từ 6 xuống 2

Trong dữ liệu mẫu, VIP của t-01 là `c-01` và `c-03`:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenantId: "t-01",
      segment: "VIP"
    }
  },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      joined: { $size: "$orders" }
    }
  }
])
~~~

Kết quả:

~~~text
c-01 => joined 3
c-03 => joined 6
~~~

Tổng số match đi qua phần join cho API này là **9**, không phải 17 của toàn bộ sáu customers.

### 9.3. Trường hợp không được đẩy `$match` lên trước

Nếu filter cần biết **dữ liệu đã join** như:

~~~javascript
{ $match: { "orders.status": "PAID" } }
~~~

thì không thể đơn giản chuyển nó lên trước `$lookup` vì `orders` chưa tồn tại trên local document. Cần xét lại ý định:

- Chỉ giữ khách có **ít nhất một** order PAID?
- Hay chỉ đưa **những order PAID** vào mảng?
- Hay lấy **top 2 order PAID mới nhất của mỗi customer**?

Ba yêu cầu khác nhau dẫn đến ba pipeline khác nhau. Tối ưu phải giữ đúng ngữ nghĩa.

## 10. Filter ở foreign pipeline: giảm số match và kích thước mảng

### 10.1. Filter sau `$lookup` không tự loại những order không phù hợp khỏi mảng

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  {
    $match: {
      "orders.status": "PAID"
    }
  }
])
~~~

`$match` bên ngoài chọn customer có **ít nhất một** order PAID, nhưng mảng `orders` vẫn có thể chứa các order CREATED, REFUNDED hoặc CANCELLED khác của customer đó. Query vẫn có thể đưa nhiều order không cần hiển thị vào document sau join.

### 10.2. Filter PAID ở phía foreign

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        { $match: { status: "PAID" } },
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "paidOrders"
    }
  }
])
~~~

Với bộ lab, `c-01` chỉ có hai order PAID trong ba order; `c-03` có năm order PAID trong sáu order. Mảng `paidOrders` nhỏ hơn và đúng mục tiêu “đưa những order đã thanh toán vào kết quả”.

### 10.3. Có phải `$match` bên trong luôn nhanh hơn?

Không tự động. Filter `status = PAID` có thể kém chọn lọc nếu 95% orders đều PAID, và index phải phù hợp để tránh quét không cần thiết. Nhưng đưa điều kiện lọc về **phía collection đang được tra cứu** giúp engine có cơ hội loại document từ sớm và giảm payload.

Index ứng viên:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1,
    status: 1,
    createdAt: -1
  },
  { name: "idx_order_customer_status_date" }
)
~~~

Đánh giá trên query thực: nếu thường chỉ cần status PAID, vị trí status trước createdAt có thể hữu ích. Nếu API cần mọi status và sort theo createdAt, index khác có thể phù hợp hơn. Đừng tạo một index khổng lồ “bao hết field” mà không xét query shape.

## 11. Projection: mỗi phần tử nhỏ hơn, mảng join cũng nhỏ hơn

Giả sử một order document có:

~~~javascript
{
  _id: "o-101",
  customerCode: "U100",
  tenantId: "t-01",
  status: "PAID",
  amount: NumberDecimal("100"),
  createdAt: ISODate("2026-09-01T08:00:00Z"),
  items: [ /* hàng trăm item */ ],
  shippingDetails: { /* payload giao vận */ },
  auditTrail: [ /* lịch sử lớn */ ],
  externalRawResponse: { /* JSON lớn */ }
}
~~~

Nếu mục tiêu API chỉ hiển thị **hai order mới nhất với mã, số tiền và ngày**, việc kéo toàn bộ `items`, `auditTrail` và raw response vào `$lookup` rất lãng phí.

### 11.1. Projection bên trong foreign pipeline

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      as: "orderSummaries"
    }
  }
])
~~~

Mỗi foreign phần tử trong `orderSummaries` chỉ mang các field được chọn. Điều này có thể giảm kích thước output và lượng dữ liệu trung gian.

### 11.2. Projection sau join có thể là quá muộn cho một số chi phí

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  {
    $project: {
      name: 1,
      "orders._id": 1,
      "orders.amount": 1
    }
  }
])
~~~

Logic output có thể nhỏ hơn nhờ projection cuối, nhưng về mặt thiết kế, `$lookup` đã được yêu cầu gắn các order document trước khi dự án cắt bớt field. Một số optimizer có thể đẩy hoặc rút gọn thao tác khi hợp lệ; **không nên dựa vào khả năng đó như bảo đảm**.

Đưa projection vào foreign pipeline sẽ biểu đạt rõ ràng những field cần lấy. Tuy nhiên, projection không bảo đảm tránh đọc document gốc nếu index không cover; phải đo `totalDocsExamined`.

### 11.3. Không lấy thiếu field cần cho nghiệp vụ

Projection quá hẹp có thể làm mất dữ liệu cần đối chiếu hoặc tính tổng. Đặc biệt:

- Nếu cần audit, phải giữ những ID/metadata cần thiết.
- Nếu API cần đối chiếu tenant, đừng bỏ hết thông tin liên quan mà không kiểm tra correctness trước.
- Khi cần sắp xếp theo field, đặt `$sort` trước khi loại field đó.

Tối ưu byte phải giữ đúng contract của API.

## 12. `$limit` trong foreign pipeline: chặn số phần tử mỗi customer

Trong nhiều giao diện, người dùng không cần **mọi order từ trước tới nay**; họ chỉ muốn **hai order gần nhất**.

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $sort: {
            createdAt: -1,
            _id: 1
          }
        },
        { $limit: 2 },
        {
          $project: {
            _id: 1,
            amount: 1,
            status: 1,
            createdAt: 1
          }
        }
      ],
      as: "recentOrders"
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      recentOrders: 1,
      recentCount: { $size: "$recentOrders" }
    }
  }
])
~~~

Ở đây `$limit: 2` nằm **bên trong foreign pipeline**, nên mỗi customer nhận tối đa **hai order**. Với customer `c-03` có sáu order, array `recentOrders` chỉ còn hai: `o-111` và `o-110` (kể cả trạng thái CREATED vì ví dụ chưa filter status).

### 12.1. Tại sao cần sort trước limit?

Nếu chỉ:

~~~javascript
pipeline: [
  { $limit: 2 }
]
~~~

thì “hai order” không có ý nghĩa **hai order mới nhất**; MongoDB không bảo đảm thứ tự khi không khai báo sort. Dùng `createdAt:-1` và `_id:1` làm tie-breaker để có thứ tự xác định trên tập dữ liệu ổn định.

### 12.2. `$limit` ở ngoài `$lookup` là bài toán khác

~~~javascript
db.customers.aggregate([
  { $limit: 2 },
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  }
])
~~~

`$limit: 2` ngoài cùng chỉ cho **hai customers** đi vào join. Nó **không** giới hạn mỗi customer tối đa hai orders.

Tương tự, `{ $limit: 2 }` **sau `$lookup`** cũng giới hạn số local document kết quả, không cắt từng mảng `orders` còn hai phần tử.

### 12.3. Có nên giới hạn kết quả để tránh vượt 16 MiB?

Giới hạn số phần tử và projection có thể giúp giữ document nhỏ. Nhưng phải xác định lại **hợp đồng nghiệp vụ**: nếu người dùng yêu cầu *toàn bộ* orders, trả tối đa hai mà không công bố là sai. Khi dataset có thể cực lớn, nên dùng **API chi tiết riêng để phân trang orders**, thay vì trả toàn bộ children trong một customer.

## 13. Số bản ghi khớp: trung bình, P95/P99 và fan-out

Trong lab:

~~~text
6 customers
17 order matches đúng tenant
Avg = 17 / 6 ≈ 2,83 order/customer
Max = 6 (c-03)
Min = 0 (c-06)
~~~

Đây là một tập rất nhỏ, chỉ minh họa khái niệm. Trong production nên đo phân phối `m_i` theo tenant, loại customer và khoảng thời gian, không chỉ lấy trung bình.

### 13.1. Tính số match sau join

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $project: { _id: 1 } }
      ],
      as: "matchedOrderIds"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      matchCount: { $size: "$matchedOrderIds" }
    }
  },
  { $sort: { matchCount: -1, _id: 1 } }
])
~~~

Ở lab, kết quả cao nhất là `c-03` với 6; thứ hai `c-05` với 4. Tuy nhiên, **đừng làm thế trên production chỉ để đo cardinality nếu mỗi customer có thể join hàng trăm nghìn orders**: cách này vẫn tạo mảng chứa tất cả matched IDs rồi mới `$size`, có nguy cơ lớn về memory/document size. Các phần sau trình bày cách tính aggregate ở foreign side mà không tạo mảng lớn.

### 13.2. Đếm trực tiếp từ collection foreign

Với cấu trúc ví dụ, ta có thể nhóm orders theo khóa nghiệp vụ:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        customerCode: "$customerCode"
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { orderCount: -1, "_id.tenantId": 1 } }
])
~~~

Pipeline này không phải join; nó cho biết phân phối số orders theo khóa. Kết quả giúp phát hiện những customer có số match quá lớn trước khi quyết định đưa toàn bộ orders vào customer document.

Với dữ liệu lab, còn nhóm `(t-01, U500)` có một order không khớp customer nào. Tính cardinality từ foreign collection vì vậy là **thống kê tham chiếu**, không mặc nhiên bằng tổng số matched orders sau join với một tập local đã lọc.

### 13.3. Đếm phân phối bằng nhóm cấp hai

Nếu muốn xem có bao nhiêu khóa foreign có 1, 2, 3, ... orders:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        customerCode: "$customerCode"
      },
      ordersPerKey: { $sum: 1 }
    }
  },
  {
    $group: {
      _id: "$ordersPerKey",
      numberOfKeys: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Đây là cách khảo sát fan-out mà không nhúng toàn bộ document order vào từng customer. Với dữ liệu thật lớn, `$group` có thể tốn bộ nhớ và cần index/phân lô/triển khai phù hợp.

## 14. Vì sao một foreign index có thể cứu chi phí join?

Hãy xét ước lượng đơn giản:

~~~text
N = 10.000 customers sau local $match
Foreign collection = 5.000.000 orders
Mỗi customer trung bình 12 orders
~~~

Nếu mỗi lượt tìm foreign matches phải quét gần toàn bộ 5 triệu orders, công việc đọc có thể cực lớn. Đây **không phải cam kết MongoDB luôn thực thi nested-loop một cách ngây thơ**, vì engine có nhiều kế hoạch khác nhau, nhưng giúp thấy rủi ro của join không index.

Khi foreign key có index phù hợp, engine có thể định vị vùng key của customer và đọc những ứng viên tương ứng, giảm mạnh lượng foreign data phải xét. Tuy nhiên:

- Vẫn có chi phí thiết lập/đọc index cho các lookup.
- Nếu một customer có 100.000 orders, index chỉ giúp **tìm đúng 100.000**; nó không làm 100.000 document biến mất.
- Nếu foreign projection cần field ngoài index, có thể cần FETCH document.
- Nếu có filter khác mà index không hỗ trợ, engine có thể phải quét nhiều key trong vùng customer.
- Cache locality và sharding ảnh hưởng rất lớn đến latency.

**Index giải quyết việc tìm foreign matches; cardinality và payload size giải quyết việc phải mang bao nhiêu dữ liệu đi tiếp.** Tối ưu một yếu tố không thay thế hai yếu tố còn lại.

### 14.1. Đặt câu hỏi bằng ba số liệu

Cho mỗi query `$lookup` quan trọng, thu:

| Nhóm số liệu | Ví dụ cần biết | Vấn đề nếu cao |
|---|---|---|
| Local input | 50.000 customers vào lookup | Quá nhiều lượt/đầu vào cần xử lý |
| Foreign scan | 3.000.000 docsExamined | Foreign index hoặc filter chưa hiệu quả |
| Match/output | 500.000 order matches, payload 500 MiB | Mảng lớn, unwind tăng, mạng và memory |

Một query có **ít foreign docs examined nhưng kết quả khổng lồ** vẫn có thể chậm. Ngược lại, query trả rất ít dữ liệu nhưng **scan hàng triệu foreign documents** cũng không thể coi là tối ưu.

## 15. Kích thước document sau `$lookup` và giới hạn 16 MiB

MongoDB có giới hạn kích thước một BSON document thông thường là **16 MiB**. Khi `$lookup` nhúng mảng orders vào customer, document kết quả có thể vượt giới hạn này nếu số order hoặc kích thước order quá lớn. Những điểm cần lưu ý:

- `$lookup` không tạo một quan hệ ảo vô hạn miễn phí; nó **gắn dữ liệu thực vào document pipeline**.
- Dù output cuối chỉ cần vài field, một thiết kế gắn cả collection children vào một mảng lớn có thể gây lỗi hoặc áp lực tài nguyên ở stage trung gian.
- Giới hạn 16 MiB của một document **khác** với giới hạn bộ nhớ của một số stage aggregation và khác tổng dung lượng response từ nhiều document.
- MongoDB có một số quy tắc về kích thước document trung gian của pipeline, nhưng không nên dựa vào ngoại lệ nội bộ để xây document join quá lớn; đầu ra BSON cuối cùng vẫn có giới hạn.

### 15.1. Bài toán ước lượng payload

Giả sử:

~~~text
Kích thước customer document:               2 KiB
Order sau join (chưa projection):             8 KiB
Số order match một customer:               3.000

Payload order xấp xỉ: 3.000 × 8 KiB = 24.000 KiB ≈ 23,4 MiB
~~~

Ngay chỉ phần orders đã lớn hơn 16 MiB. Thêm overhead mảng, field name và customer document càng vượt giới hạn. Lúc này không nên tiếp tục `$lookup` toàn bộ orders chỉ để trả customer kèm danh sách.

### 15.2. Ba biện pháp ưu tiên

1. **Giảm số match:** đặt `$match` và `$limit` đúng trong foreign pipeline, nếu contract cho phép.
2. **Giảm byte mỗi match:** `$project` chỉ những field cần thiết.
3. **Đổi giao diện dữ liệu:** trả customer metadata riêng và cung cấp endpoint phân trang orders; hoặc chỉ trả count/summary.

### 15.3. Không lẫn `allowDiskUse` với việc vượt 16 MiB

`allowDiskUse: true` cho phép một số stage aggregation ghi tạm ra disk khi vượt giới hạn bộ nhớ tương ứng, tùy phiên bản/cấu hình. Nó **không** nâng giới hạn 16 MiB của BSON document trả ra. Nếu pipeline tạo một customer document với một mảng orders quá lớn, bật `allowDiskUse` không biến document đó thành hợp lệ.

## 16. `$unwind` và sự phình số document sau join

Với join đúng tenant, ta có:

~~~text
Customer c-01 -> 3 orders
Customer c-02 -> 2 orders
Customer c-03 -> 6 orders
Customer c-04 -> 2 orders
Customer c-05 -> 4 orders
Customer c-06 -> 0 orders
~~~

`$lookup` giữ **6 customers**. Nếu `$unwind` không `preserveNullAndEmptyArrays`:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  { $unwind: "$orders" },
  { $count: "rows" }
])
~~~

Kết quả:

~~~javascript
[{ rows: 17 }]
~~~

### 16.1. Giữ cả khách không có order

~~~javascript
{
  $unwind: {
    path: "$orders",
    preserveNullAndEmptyArrays: true
  }
}
~~~

Nếu thay `$unwind` trên bằng tùy chọn preserve, tập lab có **18 document** sau unwind: 17 dòng tương ứng order khớp, cộng **một dòng** của `c-06` không có order.

### 16.2. Vì sao cần phân biệt số output và kích thước output?

Sau unwind, mỗi document thường chỉ mang một order, tránh mảng lớn một document, nhưng **toàn bộ thông tin customer bị lặp trên từng dòng**. Nếu customer có thông tin profile lớn, số byte sau unwind có thể tăng mạnh vì metadata local được lặp lại.

Pipeline:

~~~javascript
db.customers.aggregate([
  /* lookup đúng tenant */,
  { $unwind: "$orders" },
  {
    $project: {
      _id: 1,
      customerCode: 1,
      orderId: "$orders._id",
      amount: "$orders.amount"
    }
  }
])
~~~

giữ output mỗi dòng nhỏ hơn bằng cách chỉ trả field cần thiết. Đừng mang cả profile local và toàn bộ order payload qua nhiều stage nếu chỉ cần báo cáo `customerCode + amount`.

## 17. Join nhiều lần có thể nhân fan-out

Giả sử mỗi customer có:

~~~text
10 orders
5 support tickets
3 subscriptions
~~~

Nếu dùng ba `$lookup` và giữ kết quả là **ba mảng riêng**, số document local vẫn là một customer, nhưng kích thước customer tăng theo ba mảng.

Nếu tiếp tục:

~~~javascript
{ $unwind: "$orders" },
{ $unwind: "$tickets" },
{ $unwind: "$subscriptions" }
~~~

thì một customer có thể biến thành:

~~~text
10 × 5 × 3 = 150 document
~~~

Đây là **Cartesian-like multiplication** do các mảng độc lập bị unwind nối tiếp. Nếu bạn muốn tổng orders và tổng tickets, cách nhân dòng này thường là sai về ngữ nghĩa thống kê: một order xuất hiện 15 lần, dẫn đến `$sum` bị nhân.

### 17.1. Ví dụ sai tổng doanh thu

~~~text
Customer A:
  Orders: 2 orders, amount 100 và 200
  Tickets: 3 tickets

Đúng: totalRevenue = 300

Sau unwind orders rồi unwind tickets:
  2 × 3 = 6 dòng
  Nếu sum orders.amount: 100×3 + 200×3 = 900 (SAI)
~~~

### 17.2. Cách tốt hơn

- Tính doanh thu trong foreign `$lookup` pipeline rồi chỉ trả một summary.
- Tính số tickets ở nhánh join khác.
- Giữ các mảng riêng nếu cần hiển thị, tránh unwind đồng thời khi không cần.
- Hoặc group lại đúng cấp, sử dụng distinct/order ID khi nghiệp vụ thực sự yêu cầu xử lý quan hệ phức tạp.

**Quy tắc:** trước khi thêm `$unwind` thứ hai, hãy ước lượng **tích các số phần tử** trong những mảng độc lập, không chỉ tổng.

## 18. Khi chỉ cần số lượng: đếm ở foreign side, đừng kéo cả mảng

Một UI có thể chỉ cần:

~~~javascript
{
  customerId: "c-03",
  name: "Chi",
  orderCount: 6
}
~~~

Truy vấn kém hiệu quả nếu lấy toàn bộ orders rồi mới tính `$size`:

~~~javascript
// Không phù hợp với customer có hàng trăm nghìn orders.
[
  { $lookup: { /* trả toàn bộ orders */, as: "orders" } },
  { $project: { orderCount: { $size: "$orders" } } }
]
~~~

### 18.1. `$count` ngay trong foreign pipeline

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: {
        t: "$tenantId",
        code: "$customerCode"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $count: "total" }
      ],
      as: "orderStats"
    }
  },
  {
    $set: {
      orderCount: {
        $ifNull: [
          { $first: "$orderStats.total" },
          0
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      tenantId: 1,
      customerCode: 1,
      orderCount: 1
    }
  },
  { $sort: { _id: 1 } }
])
~~~

Thay vì tạo mảng chứa nhiều order documents, `orderStats` chỉ có thể chứa một document dạng `{total: N}` hoặc mảng rỗng khi không có match.

Với lab:

~~~text
c-01 -> 3
c-02 -> 2
c-03 -> 6
c-04 -> 2
c-05 -> 4
c-06 -> 0
~~~

### 18.2. Đếm ở foreign side vẫn có chi phí

`$count` giảm **kích thước dữ liệu trả về và memory của mảng join**, nhưng server vẫn cần xét những order match để đếm, trừ khi có tối ưu phù hợp. Nếu API cần count rất thường xuyên cho hàng triệu customers, có thể cần:

- Pre-aggregated counters.
- Materialized view/summary collection.
- Counter trong customer document được cập nhật đồng bộ với order lifecycle.
- Job reconciliation để sửa sai lệch.

Không tuyên bố `$count` miễn phí chỉ vì output một document.

### 18.3. Khi cần tổng tiền thay vì count

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            status: "PAID",
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        {
          $group: {
            _id: null,
            paidOrderCount: { $sum: 1 },
            paidRevenue: { $sum: "$amount" }
          }
        },
        {
          $project: {
            _id: 0,
            paidOrderCount: 1,
            paidRevenue: 1
          }
        }
      ],
      as: "paidStats"
    }
  }
])
~~~

`paidStats` chỉ là một phần tử summary (nếu có paid orders) thay vì nhiều full orders. Khi không có paid orders, mảng rỗng; API có thể chuẩn hóa count/revenue về 0 bằng `$ifNull` và `$first` hoặc xử lý kết quả ở tầng ứng dụng.

## 19. Top-N mỗi customer: thay “tất cả” bằng dữ liệu cần hiển thị

Đối với dashboard, thường cần:

~~~text
Customer
  name
  lastTwoPaidOrders
  paidOrderCount
~~~

Cách thiết kế nên tách:

- **Top-N detail**: lấy tối đa 2 orders PAID theo createdAt.
- **Count**: tổng PAID orders, có thể qua một summary query/join khác hoặc pre-aggregate.

### 19.1. Lấy top 2 PAID trong foreign pipeline

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            status: "PAID",
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $sort: { createdAt: -1, _id: 1 } },
        { $limit: 2 },
        { $project: { _id: 1, amount: 1, createdAt: 1 } }
      ],
      as: "lastTwoPaidOrders"
    }
  }
])
~~~

Với `t-01`:

~~~text
c-01: o-102, o-101       (o-103 REFUNDED không khớp)
c-02: o-104              (o-105 CREATED không khớp)
c-03: o-111, o-109       (hai PAID mới nhất)
c-06: []                 (không có order)
~~~

### 19.2. Index ứng viên cho top-N

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    customerCode: 1,
    status: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "idx_paid_orders_by_customer_date" }
)
~~~

Trong query có equality trên tenant/customer/status, những field sort tiếp theo là createdAt và ID. Nhưng khả năng phục vụ sort index trong foreign pipeline correlated còn phụ thuộc cách planner index các biểu thức `$expr`. Hãy kiểm tra plan và số key examined, không tự giả định index chắc chắn “đọc đúng hai key”.

### 19.3. Tổng count có bị giới hạn về 2 không?

Nếu bạn tính:

~~~javascript
{ $size: "$lastTwoPaidOrders" }
~~~

thì kết quả cao nhất là 2, **không phải tổng số paid orders**. Với `c-03` có 5 paid orders, count từ mảng top 2 chỉ là 2. Nếu API cần tổng số, phải có phép đếm riêng hoặc materialized counter.

Đây là lỗi correctness rất phổ biến khi tối ưu `$lookup` bằng `$limit` mà quên thay đổi ý nghĩa của `$size`.

## 20. Phân trang local documents trước hay sau join?

Giả sử API danh sách customers có trang 20 khách, mỗi khách kèm hai order mới nhất. Một pipeline có thể:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  { $sort: { name: 1, _id: 1 } },
  { $skip: 0 },
  { $limit: 20 },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $sort: { createdAt: -1, _id: 1 } },
        { $limit: 2 },
        { $project: { _id: 1, amount: 1, createdAt: 1 } }
      ],
      as: "recentOrders"
    }
  }
])
~~~

Ý nghĩa: chọn 20 customers trên **một trang customers**, rồi chỉ join orders cho những khách đó. Nếu `$lookup` chạy trước `$skip/$limit`, có thể phải join nhiều customers mà cuối cùng không xuất hiện trên trang.

### 20.1. Khi nào được phân trang trước join?

Khi thứ tự/trang được quyết định hoàn toàn bởi **field local**, và join **không dùng để quyết định khách nào được giữ hoặc vị trí của họ**, phân trang local trước có thể giữ đúng kết quả đồng thời giảm N.

### 20.2. Khi nào không được?

Nếu yêu cầu:

> Trả 20 customers có **tổng tiền PAID cao nhất**.

thì không thể lấy 20 customers theo tên trước rồi join/tính tổng: bạn sẽ chỉ xếp hạng 20 khách đã chọn, bỏ qua những khách có revenue lớn ở ngoài trang. Cần tính/biết revenue cho toàn tập ứng viên, sau đó mới sort và limit — hoặc dùng summary precomputed.

Tương tự, nếu filter:

> Chỉ customers có ít nhất 3 PAID orders.

thì việc giới hạn local trước khi tính số orders có thể khiến trang chưa đủ kết quả và bỏ sót khách phù hợp nằm phía sau.

**Tối ưu sớm không được thay đổi tập ứng viên mà người dùng muốn phân trang.**

## 21. `$match` sau `$unwind` và điều kiện trên joined data

Cách thường gặp để lấy từng order PAID kèm customer:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        }
      ],
      as: "orders"
    }
  },
  { $unwind: "$orders" },
  { $match: { "orders.status": "PAID" } },
  {
    $project: {
      _id: 1,
      customerCode: 1,
      orderId: "$orders._id",
      amount: "$orders.amount"
    }
  }
])
~~~

Về ngữ nghĩa, output chỉ gồm dòng cho những order PAID, nhưng pipeline có thể đã join và unwind cả order không PAID trước khi lọc.

### Đẩy filter foreign vào `$lookup`

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            status: "PAID",
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $project: { _id: 1, status: 1, amount: 1 } }
      ],
      as: "paidOrders"
    }
  },
  { $unwind: "$paidOrders" }
])
~~~

Đây là cách biểu đạt trực tiếp “chỉ join order PAID”. Trong một số pipeline, MongoDB optimizer có khả năng **coalesce `$lookup + $unwind`, thậm chí đẩy `$match` trên field joined vào lookup** khi chứng minh an toàn; hãy đọc `explain` để xem plan thực tế. Không cần cố tình viết pipeline khó hiểu chỉ để trông ngắn nếu không thể kiểm chứng optimizer.

## 22. Đọc `explain("executionStats")` cho `$lookup`

Thay vì chỉ quan sát thời gian ở ứng dụng, hãy kiểm tra kế hoạch:

~~~javascript
db.customers.explain("executionStats").aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $project: { _id: 1, amount: 1 } }
      ],
      as: "orders"
    }
  }
])
~~~

### 22.1. Những trường thống kê quan trọng

Tùy phiên bản MongoDB/engine, `explain` của lookup có thể thể hiện:

| Trường / stage | Điều cần hiểu |
|---|---|
| `$cursor` | Cách đọc local collection |
| `IXSCAN` | Đọc index key ở kế hoạch tương ứng |
| `COLLSCAN` | Quét collection |
| `FETCH` | Lấy document sau index scan |
| `EQ_LOOKUP` | Biểu diễn một equality lookup ở những kế hoạch Slot-Based Execution phù hợp |
| `indexesUsed` | Tên index foreign được dùng, khi thống kê được cung cấp |
| `totalKeysExamined` | Tổng index keys đã xét ở stage tương ứng |
| `totalDocsExamined` | Tổng document đã xét ở stage tương ứng |
| `collectionScans` | Số lượt collection scan liên quan đến lookup, khi có metric |
| `nReturned` | Số document được trả ở stage tương ứng |
| `executionTimeMillisEstimate` | Ước lượng thời gian stage, nếu được cung cấp |

**Không tự giả định** mọi MongoDB version đều in `EQ_LOOKUP` hoặc `indexesUsed` với cùng đường dẫn JSON. Các kế hoạch sử dụng classic engine, SBE, có/không foreign pipeline hoặc từ sharded collection có thể có hình dạng khác nhau.

### 22.2. `EQ_LOOKUP` là gì?

Trong những trường hợp đủ điều kiện, MongoDB có thể thực hiện equality `$lookup` bằng Slot-Based Execution engine, và plan có thể biểu diễn stage `EQ_LOOKUP`. Những điều kiện như lookup có foreign pipeline, sử dụng numeric path components hoặc from collection thuộc loại đặc biệt có thể ảnh hưởng khả năng dùng execution mode này theo phiên bản. Không lấy sự vắng mặt của chuỗi `EQ_LOOKUP` làm bằng chứng duy nhất rằng join chậm.

Đối với `$lookup` có `pipeline/let/$expr`, khả năng index và cách thực thi có thể khác equality lookup đơn giản. Hãy tập trung vào **keys/docs examined, index thực sự sử dụng và cardinality/output**, thay vì chỉ tên stage.

### 22.3. Phân tích phần local và foreign riêng

Với một pipeline có:

~~~text
$match local -> $lookup foreign -> $unwind -> $sort
~~~

hãy hỏi:

1. Bao nhiêu customers được đọc trước `$lookup`?
2. Bao nhiêu customers thực sự vào `$lookup`?
3. Foreign side có index phù hợp không?
4. Trong toàn bộ lookup, bao nhiêu keys và docs được kiểm tra?
5. Bao nhiêu order matches được gắn vào mảng?
6. Sau `$unwind`, có bao nhiêu document đi tiếp?
7. Sort sau đó phải xử lý bao nhiêu document và có spill không?

Một query có local IXSCAN tốt **vẫn có thể join rất tốn kém** nếu foreign side phải collection scan nhiều lần.

### 22.4. Kiểm tra đường truy cập foreign bằng query tương tự

~~~javascript
db.orders.find({
  tenantId: "t-01",
  customerCode: "U300"
}).sort({
  createdAt: -1,
  _id: 1
}).limit(2).explain("executionStats")
~~~

Lệnh này giúp xem index `orders` có hữu ích cho access pattern cụ thể hay không. Nhưng foreign pipeline correlated có `$expr` có thể khác về indexability; **phải kiểm tra cả `explain` của pipeline join thật**.

### 22.5. Trên dữ liệu 6 customers/18 orders không thể kết luận hiệu năng

MongoDB có thể chọn COLLSCAN vì collection quá nhỏ; chênh lệch vài micro/mili giây không ổn định. Lab nhằm chứng minh **cardinality và query semantics**. Muốn benchmark index cần dữ liệu nhiều hơn, phân phối skewed như production, số request đồng thời, cache state, replica/shard topology và SLO đo được.

## 23. Thứ tự stage và tối ưu plan

Một query hiển thị danh sách customers cùng số đơn hàng:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  { $project: { _id: 1, tenantId: 1, customerCode: 1, name: 1 } },
  {
    $lookup: {
      from: "orders",
      let: { t: "$tenantId", code: "$customerCode" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$tenantId", "$$t"] },
                { $eq: ["$customerCode", "$$code"] }
              ]
            }
          }
        },
        { $count: "total" }
      ],
      as: "stats"
    }
  },
  { $set: { totalOrders: { $ifNull: [{ $first: "$stats.total" }, 0] } } },
  { $project: { stats: 0 } },
  { $sort: { name: 1, _id: 1 } }
])
~~~

Các stage trước lookup giúp thu hẹp local inputs và field local; lookup chỉ trả count; stage sau tạo output cần thiết. Tuy nhiên, nếu API muốn xếp khách theo `totalOrders` giảm dần, sort phải **sau** khi tạo `totalOrders`:

~~~javascript
{ $sort: { totalOrders: -1, _id: 1 } }
~~~

Không thể áp một `$limit` nhỏ trước lookup rồi tuyên bố đó là “top customers theo totalOrders” trên toàn bộ tập.

### 23.1. $sort đầu vào và index local

Nếu API chỉ cần 20 khách theo tên:

~~~javascript
{ $match: { tenantId: "t-01" } },
{ $sort: { name: 1, _id: 1 } },
{ $limit: 20 },
{ $lookup: { /* foreign pipeline */ } }
~~~

index:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, name: 1, _id: 1 },
  { name: "idx_customers_tenant_name_id" }
)
~~~

có thể giúp chọn top 20 local docs sớm. Điều này giảm N **nếu selection không phụ thuộc foreign data**.

### 23.2. Khi optimizer coalesce

MongoDB có thể áp dụng các tối ưu như:

- Đẩy `$match` trước những stage không làm thay đổi field liên quan.
- Gộp `$sort` + `$limit` thành top-k trong điều kiện phù hợp.
- Gộp `$lookup` và `$unwind` liền kề, đôi khi có `$match` trên field joined.

Nhưng optimizer **không thể biến đổi pipeline theo cách đổi ngữ nghĩa**. Đừng dựa vào giả định “đã có optimizer nên thứ tự stage nào cũng được”. Một `$limit` trước join và một `$limit` sau unwind thường giải hai bài toán khác nhau.

## 24. Join với nhiều match và `$facet`: lưu ý output size

Một API muốn:

~~~javascript
{
  totalCustomers: 10000,
  customers: [ /* 20 customers + order summaries */ ]
}
~~~

có thể dùng `$facet`:

~~~javascript
db.customers.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $facet: {
      metadata: [{ $count: "totalCustomers" }],
      customers: [
        { $sort: { name: 1, _id: 1 } },
        { $limit: 20 },
        {
          $lookup: {
            from: "orders",
            let: { t: "$tenantId", code: "$customerCode" },
            pipeline: [
              {
                $match: {
                  $expr: {
                    $and: [
                      { $eq: ["$tenantId", "$$t"] },
                      { $eq: ["$customerCode", "$$code"] }
                    ]
                  }
                }
              },
              { $sort: { createdAt: -1, _id: 1 } },
              { $limit: 2 },
              { $project: { _id: 1, amount: 1, createdAt: 1 } }
            ],
            as: "recentOrders"
          }
        }
      ]
    }
  }
])
~~~

`$facet` có lợi khi muốn các nhánh tính total và page từ cùng tập input, nhưng có những giới hạn bộ nhớ/kích thước kết quả riêng. Vì output của facet là **một document chứa các mảng**, việc đặt một mảng customers khổng lồ trong facet cũng có thể đụng giới hạn BSON. Không xây facet với hàng trăm nghìn customer records chỉ vì join đã có `$limit` ở nơi khác.

### 24.1. Total customers khác total orders

Nhánh `metadata` ở ví dụ đếm **customers sau local match**, không đếm order matches. Nếu API cần số orders PAID, phải tính trên foreign collection hoặc summary thích hợp, tránh nhầm count ở cấp local với count của joined rows.

## 25. Null, missing và kiểu khóa join

### 25.1. Field join bị thiếu/null

Ở dạng equality `localField/foreignField`, MongoDB có quy tắc xử lý field thiếu tương tự giá trị null cho mục tiêu matching trong một số trường hợp. Nếu nhiều document cùng thiếu field join, một join bất cẩn có thể tạo ra **rất nhiều match không mong muốn**.

Ví dụ concept:

~~~javascript
// Local thiếu customerCode
{ _id: "c-missing", tenantId: "t-01" }

// Foreign thiếu customerCode
{ _id: "o-missing", tenantId: "t-01" }
~~~

Không thiết kế join quan trọng dựa vào “thiếu key thì chắc chắn không match”. Khi nghiệp vụ yêu cầu khóa hợp lệ, dùng schema validation/logic lọc và canonicalization.

### 25.2. Khác kiểu dữ liệu

~~~javascript
// Local
{ customerCode: 123 }

// Foreign
{ customerCode: "123" }
~~~

Hai giá trị có kiểu BSON khác nhau. Không mặc định MongoDB so chúng như cùng một mã. Các phép chuyển kiểu trong foreign `$expr` có thể làm mất khả năng tận dụng index, vì vậy nên chuẩn hóa khóa tại lúc ghi.

### 25.3. Khóa mảng

Với `localField` là mảng, equality `$lookup` có thể tìm foreign documents dựa trên các giá trị của mảng theo semantics được MongoDB hỗ trợ, dẫn tới fan-out cao hơn dự kiến. Nếu foreignField là mảng hoặc compound index trở thành multikey, những giới hạn về indexability cũng phải được xem xét, đặc biệt trong correlated `$expr`. Trước khi thiết kế join theo array:

- Xác định cần match **bất kỳ phần tử** hay **cùng phần tử object**.
- Ước lượng chiều dài mảng và số match.
- Dùng `$elemMatch` khi điều kiện nhiều field phải áp dụng lên cùng phần tử.
- Kiểm tra index và explain cho loại array thực tế.

### 25.4. Collation

Join string equality có thể chịu ảnh hưởng của collation được sử dụng ở cấp operation/collection. Nếu index foreign được tạo với collation không tương thích query, optimizer có thể không tận dụng được nó cho phần so sánh string như dự kiến. Hãy giữ key ID ở dạng chuẩn hóa ổn định, tránh xây identity dựa vào so sánh tên hiển thị theo locale.

## 26. Sharded collections và chi phí phân tán

Trong sharded cluster, `$lookup` có thể cần đọc foreign data qua nhiều shard. MongoDB hỗ trợ `$lookup` từ sharded `from` collection trong các phiên bản hiện đại (ví dụ MongoDB 5.1 trở đi), nhưng hành vi chi tiết về routing và query plan thay đổi theo phiên bản/topology.

### 26.1. Cùng key join chưa chắc cùng shard

Nếu `orders` shard theo một field không liên quan đến điều kiện foreign lookup, việc tìm order của một customer có thể cần fan-out tới nhiều shard. Việc có secondary index tốt trên từng shard không hoàn toàn xóa chi phí định tuyến và mạng.

Ngược lại, filter chứa shard key phù hợp có thể giúp định tuyến hiệu quả hơn trong điều kiện được hỗ trợ. Đừng tự suy ra rằng cứ thêm `tenantId` vào index là tất cả lookup sẽ tự động target một shard; **shard key và index key là hai thiết kế liên quan nhưng khác nhau**.

### 26.2. Các yếu tố đo riêng

- Số shard bị truy vấn cho mỗi lookup.
- Lượng dữ liệu truyền giữa shard/merger.
- Latency mạng, độ lệch shard và tenant nóng.
- Độ chọn lọc foreign key trên từng shard.
- Sort/limit có được áp gần nơi dữ liệu nằm hay phải hợp nhất sau đó.
- Spill, memory và giới hạn kết quả.

Nếu một customer có hàng triệu orders, shard dữ liệu tốt vẫn không làm kết quả “join toàn bộ orders vào một document” trở nên phù hợp với giới hạn 16 MiB.

## 27. Khi nào nên thay `$lookup` bằng data model khác?

### 27.1. Nhúng document khi quan hệ nhỏ và có giới hạn

Nếu mỗi đơn hàng luôn có một số dòng sản phẩm nhỏ và những dòng đó luôn được đọc cùng đơn, nhúng `items` trong order document có thể phù hợp hơn một join độc lập. Nhưng với **customer → orders** tăng vô hạn theo thời gian, nhúng toàn bộ orders vào customer sẽ gây tăng document không giới hạn.

**Nguyên tắc:** quan hệ 1:N có N **bounded** và lifecycle gần nhau có thể nhúng; N unbounded và cần phân trang/tìm kiếm độc lập thường hợp lý hơn khi tham chiếu sang collection riêng.

### 27.2. Denormalize một phần field ổn định

Nếu API order list cần customer name để hiển thị, có thể lưu:

~~~javascript
{
  _id: "o-101",
  customerId: "c-01",
  customerNameSnapshot: "An",
  amount: NumberDecimal("100")
}
~~~

Nhờ đó danh sách orders không phải join customers cho mỗi item. Đánh đổi: tên snapshot có thể cũ nếu customer đổi tên, cần định nghĩa đó là **tên tại thời điểm đặt đơn** hay tên hiện tại.

### 27.3. Pre-aggregation cho dashboard

Với dashboard cần doanh thu và số đơn theo customer, materialized summary:

~~~javascript
{
  _id: { tenantId: "t-01", customerCode: "U300" },
  paidOrderCount: 5,
  paidRevenue: NumberDecimal("610"),
  lastPaidOrderAt: ISODate("2026-09-06T09:00:00Z")
}
~~~

cho phép đọc một document summary thay vì scan/aggregate nhiều orders trong mỗi request.

Đánh đổi:

- Phải cập nhật khi order CREATED → PAID, PAID → REFUNDED hoặc xóa.
- Có thể cần transaction/outbox/event consumer để đồng bộ.
- Cần reconciliation vì retry và sự cố có thể gây lệch summary.
- Phải quyết định freshness của dashboard là near-real-time hay eventual.

### 27.4. API riêng để phân trang children

Thay vì:

~~~http
GET /customers/c-03?includeAllOrders=true
~~~

có thể thiết kế:

~~~http
GET /customers/c-03
GET /customers/c-03/orders?limit=20&cursor=...
~~~

Truy vấn orders theo khóa tenant/customer và sort/pagination với index phù hợp. Đây là cách tránh mảng join lớn và có thể scale tốt khi customer có lịch sử order dài.

### 27.5. Join trong ứng dụng vs `$lookup`

Join phía ứng dụng bằng **N query riêng** cho N customers có thể tạo **N+1 query problem** và nhiều network round-trip. `$lookup` có thể giảm round-trip và tận dụng xử lý server-side.

Nhưng ngược lại, nếu cần batch một số keys, query orders bằng `$in` có scope tenant rồi nhóm kết quả tại ứng dụng cũng là một phương án cần đánh giá:

~~~javascript
db.orders.find({
  tenantId: "t-01",
  customerCode: { $in: ["U100", "U200", "U300"] }
})
~~~

Đừng chuyển N+1 sang một query `$lookup` khổng lồ chỉ để “bớt round-trip” mà bỏ qua cardinality và document size. So sánh chi phí server, byte qua mạng và độ phức tạp consistency.

## 28. Một bảng quyết định về hiệu năng join

| Hiện tượng | Nguyên nhân có thể | Hướng khắc phục |
|---|---|---|
| `totalDocsExamined` foreign rất cao, output nhỏ | Thiếu index hoặc `$expr` không indexable | Index foreign phù hợp, chuẩn hóa khóa, xem explain |
| `nReturned` local cao, mỗi match ít | Quá nhiều local documents vào lookup | Đặt local `$match` / trang local trước khi join khi đúng ngữ nghĩa |
| Mỗi customer trả hàng nghìn orders | High fan-out, join toàn bộ history | Filter/limit foreign, API children riêng, pre-aggregate |
| Một customer đụng 16 MiB | Max cardinality/payload quá lớn | Không nhúng toàn bộ, giảm field/số match |
| Pipeline chậm sau `$unwind` | Cardinality explosion | Không unwind khi không cần, tính summary trong lookup |
| Tổng bị nhân lên sau hai `$unwind` | Cartesian product giữa mảng độc lập | Aggregate từng nhánh, tránh unwind nối tiếp |
| Nhiều match hơn dữ liệu đúng | Khóa join thiếu tenant hoặc không duy nhất | Join bằng khóa đầy đủ, unique constraints và authorization |
| Filter PAID ngoài lookup nhưng mảng vẫn to | Filter chỉ chọn customer, không lọc phần tử array | Đưa filter vào foreign pipeline |
| Top-N sai vì `$limit` đặt ngoài lookup | Giới hạn local docs thay vì mỗi mảng foreign | Sort/limit ở foreign pipeline |
| Count sai sau `$limit` foreign | Đếm top N thay vì tất cả | Count riêng hoặc precomputed counter |
| Sort có spill | Sort không được index hỗ trợ hoặc tập kết quả lớn | Index sort, giảm input, top-k, đo disk spill |
| Join chậm trên sharded cluster | Scatter-gather, network/shard skew | Đánh giá shard key/filter và routing |
| Index local tốt nhưng join vẫn chậm | Foreign scan nhiều | Tối ưu foreign access, không chỉ local |
| `$lookup` dễ đọc nhưng server tải cao | Quá nhiều join trong request path | Materialized read model, cache phù hợp, thay đổi API |

## 29. Bài thực hành: đo index, cardinality và output

Sử dụng dataset `customers` và `orders` ở mục 4. Thực hành **trên lab**, không chạy những phép tạo/drop index thử nghiệm trên production.

### Bài 1 — Join cơ bản và lỗi xuyên tenant

Chạy:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      customerCode: 1,
      count: { $size: "$orders" }
    }
  }
])
~~~

Hãy tính tổng các count và giải thích tại sao kết quả là 22 chứ không phải 17.

### Bài 2 — Join đúng tenant

Viết `$lookup` với `let` + `$expr` so sánh cả `tenantId` và `customerCode`. Dự đoán số match cho từng customer và chứng minh `c-06` vẫn tồn tại với mảng rỗng.

### Bài 3 — Index foreign

Tạo:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, customerCode: 1 },
  { name: "idx_orders_tenant_customer" }
)
~~~

Chạy `explain("executionStats")` cho pipeline đúng tenant trước/sau khi tạo index trong các môi trường lab khác nhau, nếu có dữ liệu đủ lớn. Nêu `indexesUsed`, `totalKeysExamined`, `totalDocsExamined` nếu engine trả các field đó. **Không tự bịa số liệu** nếu planner của dataset nhỏ dùng COLLSCAN.

### Bài 4 — Local filter

Chỉ lấy VIP của `t-01` rồi join. Dự đoán:

~~~text
Số customers vào lookup: 2
Tổng matched orders đúng tenant: 9
~~~

Giải thích index local và index foreign đóng vai trò khác nhau.

### Bài 5 — Filter PAID bên trong lookup

Viết join chỉ gắn PAID orders; so `count` của `c-01` và `c-03`:

~~~text
c-01 PAID: 2
c-03 PAID: 5
~~~

So sánh với `$match:{"orders.status":"PAID"}` **bên ngoài** lookup. Hai cách có trả cùng mảng không?

### Bài 6 — Foreign projection

Viết join chỉ trả `_id`, `amount` và `createdAt` của orders. Giải thích tác động lên byte output và vì sao projection không tự bảo đảm covered query.

### Bài 7 — Top 2 mỗi customer

Trong foreign pipeline:

~~~javascript
{ $sort: { createdAt: -1, _id: 1 } },
{ $limit: 2 }
~~~

Với `c-03`, dự đoán hai orders được trả khi **không** filter status; sau đó thêm `status:"PAID"` và dự đoán kết quả mới.

### Bài 8 — Đếm thay vì nhúng

Thay mảng full orders bằng `$count:"total"` trong foreign pipeline. Dùng `$ifNull` và `$first` để hiển thị `orderCount:0` cho `c-06`.

### Bài 9 — Unwind

Sau join đúng tenant, chạy:

~~~javascript
{ $unwind: "$orders" }
~~~

Giải thích vì sao có 17 output documents. Sau đó thử `preserveNullAndEmptyArrays:true` và giải thích con số 18.

### Bài 10 — Hai mảng độc lập

Một customer có hai orders và ba tickets. Nếu unwind cả hai mảng, có bao nhiêu dòng? Vì sao `$sum:"$orders.amount"` có thể bị nhân ba?

### Bài 11 — Giới hạn kích thước

Giả sử một customer có 4.000 orders, mỗi order sau join khoảng 5 KiB. Ước lượng payload foreign trước overhead. Tại sao không thể dựa vào `allowDiskUse:true` để nhúng tất cả vào một BSON document?

### Bài 12 — Phân trang local trước join

Thiết kế pipeline lấy 20 customers theo tên, mỗi khách kèm hai order mới nhất. Đặt `$match`, `$sort`, `$skip`, `$limit` ở đâu nếu filter/trang chỉ dựa trên local fields?

### Bài 13 — Trường hợp không được limit trước

Yêu cầu là “20 khách có doanh thu PAID lớn nhất”. Giải thích vì sao chọn trước 20 customers rồi tính revenue sẽ sai. Đề xuất dùng summary view hoặc aggregation trên toàn tập ứng viên.

### Bài 14 — Production index và deployment

Bạn có hai query:

1. Dashboard theo tenant + customer, chỉ lấy hai orders gần nhất.
2. Báo cáo toàn tenant lọc orders theo ngày.

Đề xuất các index ứng viên khác nhau và giải thích vì sao một index `{tenantId,customerCode,createdAt}` không mặc định tối ưu query chỉ có tenant + ngày.

### Bài 15 — Quan sát skew

Đề xuất metric/alert cho:

- P95/P99/max matched orders/customer.
- Số foreign docs examined trên mỗi local document.
- Tổng byte output API.
- Tỷ lệ query có spill hoặc BSON size error.
- Latency p95/p99 và CPU/I/O.

Tại sao trung bình 10 orders/customer có thể che giấu một customer có 500.000 orders?

## 30. Gợi ý đáp án thực hành

### Bài 1

Join chỉ theo `customerCode` làm `c-01` và `c-04` cùng nhận năm orders có mã U100 thuộc cả hai tenant. Tổng count là **22**, gồm 17 match hợp lệ và 5 lượt gắn thêm sai tenant.

### Bài 2

Khi thêm equality theo tenant, các count lần lượt là `3, 2, 6, 2, 4, 0`. `$lookup` vẫn giữ `c-06` với mảng `[]`; tổng phần tử match = 17.

### Bài 3

Index ở `orders` có thể giúp tìm những bản ghi theo key foreign. Kết quả `explain` cần xem theo phiên bản/plan; không có giá trị keys/docs examined cố định cho lab nhỏ.

### Bài 4

Chỉ `c-01` và `c-03` là VIP t-01, tương ứng 3 và 6 orders, tổng 9. Index local có thể hỗ trợ local `$match`; index foreign phục vụ tra cứu orders.

### Bài 5

`c-01` có 2 PAID, `c-03` có 5 PAID. `$match` bên ngoài `{"orders.status":"PAID"}` chỉ kiểm tra customer có ít nhất một PAID order, không tự cắt các order khác ra khỏi mảng.

### Bài 6

Projection trong foreign pipeline giảm số field mỗi matched order, giúp giảm byte trong mảng join. Nhưng nếu index không chứa những field được trả, MongoDB vẫn có thể cần FETCH document.

### Bài 7

`c-03` lấy hai order mới nhất là `o-111` (2026-09-06) và `o-110` (2026-09-05). Nếu chỉ PAID, `o-110` bị loại và hai order là `o-111`, `o-109`.

### Bài 8

Foreign `$count` tạo summary thay vì mảng full orders. Khi không có match, dùng `$ifNull:[{$first:"$orderStats.total"},0]` để trả 0.

### Bài 9

`$unwind` mặc định tạo 17 dòng matched order, bỏ `c-06`. Dùng preserve true giữ thêm một dòng của customer không có order → 18.

### Bài 10

Hai arrays độc lập có 2 và 3 phần tử tạo 2 × 3 = 6 dòng. Mỗi order bị lặp 3 lần; sum amount trực tiếp trên 6 dòng sẽ gấp ba tổng đúng.

### Bài 11

`4000 × 5 KiB = 20.000 KiB ≈ 19,5 MiB`, chưa kể local/overhead. Vượt giới hạn 16 MiB của BSON document. `allowDiskUse` không nâng giới hạn một document.

### Bài 12

Khi trang chỉ dựa trên local fields: `$match(local) → $sort(local) → $skip → $limit → $lookup(foreign top 2)`. Mục tiêu là chỉ thực hiện lookup cho customers xuất hiện trên trang.

### Bài 13

Doanh thu tổng là field **suy ra từ orders**, chưa biết khi chọn 20 customers đầu. Phải tính/đọc summary revenue cho toàn tập ứng viên trước khi sort/top 20.

### Bài 14

Dashboard: ứng viên `{tenantId:1,customerCode:1,createdAt:-1,_id:1}`; báo cáo theo tenant + ngày: ứng viên `{tenantId:1,createdAt:-1}`. Key `customerCode` chen giữa có thể làm index thứ nhất không hỗ trợ hiệu quả sort/range ngày toàn tenant.

## 31. Câu hỏi ôn tập

**1. Index nên đặt ở collection nào cho equality `$lookup`?**

Index trên foreign collection, đặc biệt `foreignField`/các điều kiện lọc của foreign pipeline, thường quan trọng để tìm nhanh match. Index local giúp lọc/sort local inputs chứ không thay foreign index.

**2. `$lookup` có làm số document pipeline tăng bằng số match không?**

Không mặc định. Nó gắn một **mảng foreign matches** vào mỗi local document. `$unwind` mới biến phần tử mảng thành nhiều document.

**3. Fan-out là gì?**

Số foreign documents khớp với mỗi local document. Tổng matched elements là tổng fan-out của các local documents; sau unwind có thể trở thành số dòng output.

**4. Vì sao phải đo cả max matches, không chỉ trung bình?**

Một local key có quá nhiều matches có thể làm document join vượt 16 MiB, dù trung bình rất thấp.

**5. Thêm index foreign có làm mảng kết quả nhỏ lại không?**

Không. Index giúp định vị match, còn số match phụ thuộc dữ liệu và điều kiện join. Muốn mảng nhỏ phải lọc, giới hạn, project hoặc thay đổi API.

**6. `$match` local trước `$lookup` giúp gì?**

Giảm số local documents cần lookup nếu filter không phụ thuộc dữ liệu foreign. Việc giảm N có thể giảm đáng kể tổng công việc.

**7. Tại sao `$match` theo status của orders sau `$lookup` không tự cắt mảng?**

Nó chọn local documents thỏa predicate trên mảng, còn mảng đã join có thể vẫn chứa phần tử không thỏa. Filter foreign nên đặt trong foreign pipeline khi muốn chỉ lấy phần tử hợp lệ.

**8. `$limit` trong foreign pipeline khác `$limit` ngoài lookup ra sao?**

Trong foreign pipeline, nó giới hạn số foreign matches của **mỗi local document**; bên ngoài, nó giới hạn số local documents/rows ở stage tương ứng.

**9. `$project` trong foreign pipeline có tác dụng gì?**

Giảm field của mỗi matched foreign document, nhờ vậy có thể giảm kích thước mảng/output. Không tự bảo đảm có covered query.

**10. Vì sao hai `$unwind` có thể làm tổng tiền sai?**

Nếu unwind hai mảng độc lập, số dòng có thể là tích số phần tử; giá trị ở mảng thứ nhất bị lặp theo số phần tử của mảng thứ hai.

**11. `$count` ở foreign side có giải quyết tất cả chi phí lookup không?**

Không. Nó giảm kích thước data trả về, nhưng thường vẫn phải xét matched foreign documents để đếm.

**12. Giới hạn 16 MiB và `allowDiskUse` liên quan nhau thế nào?**

16 MiB giới hạn kích thước một BSON document thông thường; `allowDiskUse` chỉ liên quan cho phép một số stage spill ra disk khi cần, không nâng giới hạn document.

**13. `$expr` trong lookup có luôn dùng index không?**

Không. Một số field–constant comparisons có thể dùng index trong điều kiện phù hợp; field–field comparisons, biến thiếu, multikey/sparse/partial indexes hoặc expression biến đổi field có thể hạn chế indexability.

**14. Khi nào cần kiểm tra `EQ_LOOKUP`?**

Khi đọc `explain` của equality lookup ở phiên bản có Slot-Based Execution support. Không phải mọi lookup đều có stage đó, nên cũng phải xem keys/docs examined và index use.

**15. Tại sao join chỉ theo `customerCode` nguy hiểm trong multi-tenant?**

Vì customerCode có thể trùng giữa tenant; join sai làm trả dữ liệu cross-tenant và tăng số match. Phải bổ sung tenant scope vào join hoặc dùng khóa toàn cục duy nhất đã được xác thực.

**16. Có thể phân trang customers trước lookup không?**

Có khi page/filter/sort chỉ phụ thuộc local fields. Không được nếu thứ tự hoặc filter trang phụ thuộc dữ liệu đã join.

**17. Khi nào pre-aggregate tốt hơn lookup toàn bộ orders?**

Khi dashboard chỉ cần count/sum/top summary thường xuyên và orders history lớn, một summary được cập nhật đáng tin cậy có thể giảm tải request path.

**18. Dữ liệu được shard có tự làm lookup rẻ hơn không?**

Không. Nếu điều kiện không giúp định tuyến tới shard liên quan, join có thể fan-out qua nhiều shard và tốn network. Cần xem shard key, routing và plan.

## 32. Checklist triển khai join có kiểm soát

- [ ] Đã xác định **đơn vị output**: local document với mảng, hay row sau unwind?
- [ ] Khóa join có đúng **tenant/owner/business identity** và kiểu dữ liệu không?
- [ ] Có local documents thiếu/null key dễ gây match ngoài ý muốn không?
- [ ] Đã đếm N local documents thực sự vào lookup?
- [ ] Đã đo avg/P95/P99/max foreign matches cho từng local key?
- [ ] Foreign collection có index phục vụ equality/pipeline filter không?
- [ ] Correlated `$expr` có khả năng dùng index ở phiên bản đang chạy không?
- [ ] Có những foreign field lớn cần cắt bằng projection không?
- [ ] Có thể filter foreign sớm để giảm số match không?
- [ ] Có thể dùng `$sort + $limit` foreign cho top-N thật sự cần hiển thị không?
- [ ] Đã phân biệt total count với count của mảng top-N chưa?
- [ ] Có nguy cơ mảng join làm BSON document vượt 16 MiB không?
- [ ] Có nhiều mảng độc lập và nhiều `$unwind` gây nhân rows không?
- [ ] Nếu phân trang local trước join, có bảo đảm không đổi thứ tự/filter nghiệp vụ không?
- [ ] Đã đọc `explain("executionStats")` cả phía local/foreign và kiểm tra `indexesUsed` khi có?
- [ ] Đã đo số key/doc examined, latency p95/p99, byte output và spill khi dataset đủ lớn chưa?
- [ ] Nếu sharded, điều kiện lookup có hỗ trợ routing hiệu quả không?
- [ ] Đã cân nhắc materialized summary/API phân trang children khi quan hệ 1:N lớn chưa?
- [ ] Có cơ chế monitoring và rollback khi thay đổi index/join query trên production chưa?

## 33. Tổng kết

Hiệu năng `$lookup` không thể đánh giá chỉ bằng câu hỏi **“có index hay chưa?”**. Cần nhìn đồng thời **ba trục**:

1. **Index/foreign access:** MongoDB phải xem bao nhiêu index keys và foreign documents để tìm match?
2. **Cardinality/fan-out:** có bao nhiêu local documents, mỗi document khớp bao nhiêu foreign documents, và điều gì xảy ra sau `$unwind`?
3. **Payload/output:** mỗi phần tử joined lớn bao nhiêu, tổng byte đi qua pipeline là bao nhiêu, có nguy cơ vượt BSON 16 MiB hoặc làm các stage sau cần memory/disk lớn không?

Với yêu cầu thực tế, thứ tự ưu tiên thường là: **join đúng khóa trước**, lọc local sớm khi ngữ nghĩa cho phép, tạo index phù hợp trên foreign collection, đưa filter/projection/top-N vào foreign pipeline khi chỉ cần subset, tránh unwind tích các mảng độc lập, và chuyển sang summary hoặc API phân trang khi quan hệ 1:N không giới hạn. Cuối cùng, dùng `explain("executionStats")` cùng cardinality và kích thước kết quả **trên workload đại diện** để chứng minh phương án tối ưu, thay vì chỉ dựa vào cú pháp hoặc những con số đo trên lab nhỏ.
