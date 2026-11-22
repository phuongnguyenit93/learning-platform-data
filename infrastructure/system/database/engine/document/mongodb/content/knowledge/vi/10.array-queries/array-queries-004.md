# Truy vấn mảng document và đường dẫn lồng nhau

MongoDB cho phép một document chứa **embedded document**, **array** và **array of documents** ở nhiều cấp. Nhờ đó, một đơn hàng có thể lưu trực tiếp các mặt hàng, mỗi mặt hàng lưu thuộc tính, nhãn và các lần phân bổ kho. Nhưng cách diễn đạt điều kiện truy vấn phải thật chính xác: một câu truy vấn có thể khớp vì **hai phần tử khác nhau** trong mảng cùng đáp ứng hai điều kiện, mặc dù không có phần tử nào đáp ứng cả hai.

Bài học thuộc chương **Truy vấn mảng** của MongoDB, tập trung vào việc tìm và xử lý **mảng các document** bằng **dot notation**, **`$elemMatch`**, đường dẫn xuyên nhiều cấp lồng nhau, projection, aggregation, cùng các giới hạn khi dùng index và cập nhật phần tử mảng. Ví dụ chạy trong **`mongosh`** với dữ liệu thực hành `array_query_lab.orders`.

Sau bài học, bạn có thể:

- Viết filter trên field của document lồng và các phần tử của array of documents.
- Phân biệt điều kiện **mỗi điều kiện có thể khớp một phần tử khác nhau** với điều kiện **cùng một phần tử phải khớp tất cả**.
- Sử dụng `$elemMatch` cho array of documents, array số và mảng lồng nhiều cấp.
- Truy vấn trường tại chỉ số mảng, trường thiếu/null, mảng rỗng, và nhiều điều kiện trên mảng.
- Phân biệt **lọc document cha** với **chọn phần tử mảng được trả về** bằng projection/aggregation.
- Hiểu tác động của **multikey index**, ranh giới index trên array, và điều kiện cập nhật bằng `$`, `$[]`, `$[identifier]`.
- Tránh các bẫy phổ biến như match nhầm phần tử, so sánh cả embedded document, dùng `$ne` sai ý nghĩa và truy vấn mảng không giới hạn.

> **Phạm vi cú pháp:** Ví dụ dùng query language của MongoDB Server trong `mongosh`. Khi chuyển sang Java Driver, Spring Data MongoDB hoặc một driver khác, cú pháp API client có thể khác, nhưng **ngữ nghĩa filter ở phía MongoDB** vẫn cần được giữ đúng. Các tùy chọn phụ thuộc phiên bản phải được đối chiếu với Database Manual của server thực tế.

## 1. Phân biệt ba cấu trúc dữ liệu

MongoDB có thể lưu các kiểu cấu trúc sau trong cùng collection:

| Cấu trúc | Ví dụ | Cách truy vấn điển hình |
|---|---|---|
| **Embedded document** | `customer: { name, address: { city } }` | `"customer.address.city": "Hà Nội"` |
| **Array of scalars** | `tags: ["book", "gift"]` | `tags: "gift"` hoặc `tags: { $all: [...] }` |
| **Array of documents** | `items: [{sku, qty}, {sku, qty}]` | `"items.sku": "BK-01"` hoặc `items: { $elemMatch: {...} }` |
| **Nested arrays inside documents** | `items[].allocations[]` | Kết hợp `$elemMatch` ở từng ranh giới cần cùng phần tử. |

Ví dụ về nhiều mức lồng:

~~~javascript
{
  _id: "O-100",
  customer: {
    id: "C-1",
    location: { city: "Hà Nội", district: "Ba Đình" }
  },
  items: [
    {
      sku: "BK-01",
      qty: 1,
      tags: ["book", "sale"],
      allocations: [
        { warehouse: "HN", qty: 1 }
      ]
    },
    {
      sku: "PN-02",
      qty: 3,
      tags: ["office"],
      allocations: [
        { warehouse: "SG", qty: 3 }
      ]
    }
  ]
}
~~~

Sơ đồ truy cập:

~~~text
Order
├── customer                         (embedded document)
│   └── location                     (embedded document)
│       ├── city
│       └── district
└── items                             (array)
    ├── [0]                          (document)
    │   ├── sku
    │   ├── qty
    │   ├── tags                     (array of strings)
    │   └── allocations              (array of documents)
    │       └── [0].warehouse
    └── [1]                          (document)
        └── allocations              (array of documents)
~~~

**Dot notation** là chuỗi đường dẫn gồm các đoạn phân tách bằng dấu chấm, ví dụ `"customer.location.city"`, `"items.sku"` hoặc `"items.allocations.warehouse"`. Nó có ý nghĩa hơi khác nhau tùy đi qua **object** hay **array**: qua object chọn một field, qua array tìm trong các phần tử có thể chứa field tương ứng.

## 2. Bộ dữ liệu thực hành có thể tái tạo

Mỗi đơn hàng chứa một mảng `items`; mỗi item có `sku`, `qty`, `tags` và một mảng `allocations` của các kho được phân bổ. Ta cố ý tạo một số đơn có **SKU và số lượng cao nằm ở hai item khác nhau**, để phân biệt kết quả filter.

Chạy trong database thử nghiệm riêng. Các lệnh `replaceOne` dưới đây có chủ ý ghi đè bốn document demo có `_id` cố định; không chạy trên dữ liệu production.

~~~javascript
const lab = db.getSiblingDB("array_query_lab")
const sampleOrders = [
  {
    _id: "O-100",
    status: "PAID",
    customer: {
      id: "C-1",
      location: { city: "Hà Nội", district: "Ba Đình" }
    },
    items: [
      {
        sku: "BK-01", qty: 1, price: 120000,
        tags: ["book", "sale"],
        attributes: { color: "blue" },
        allocations: [{ warehouse: "HN", qty: 1 }]
      },
      {
        sku: "PN-02", qty: 3, price: 10000,
        tags: ["office"],
        attributes: { color: "red" },
        allocations: [{ warehouse: "SG", qty: 3 }]
      },
      {
        sku: "BK-03", qty: 4, price: 75000,
        tags: ["book", "gift"],
        attributes: { color: "green" },
        allocations: [{ warehouse: "HN", qty: 4 }]
      }
    ],
    shipping: {
      events: [
        { code: "CREATED", at: ISODate("2026-11-01T02:00:00Z") },
        { code: "PICKED", at: ISODate("2026-11-02T03:00:00Z") }
      ]
    },
    createdAt: ISODate("2026-11-01T02:00:00Z")
  },
  {
    _id: "O-200",
    status: "NEW",
    customer: {
      id: "C-2",
      location: { city: "Đà Nẵng", district: "Hải Châu" }
    },
    items: [
      {
        sku: "BK-01", qty: 3, price: 120000,
        tags: ["book"],
        attributes: { color: "blue" },
        allocations: [
          { warehouse: "SG", qty: 1 },
          { warehouse: "HN", qty: 2 }
        ]
      },
      {
        sku: "PN-02", qty: 1, price: 10000,
        tags: ["office"],
        attributes: { color: "red" },
        allocations: [{ warehouse: "HN", qty: 1 }]
      }
    ],
    createdAt: ISODate("2026-11-03T05:00:00Z")
  },
  {
    _id: "O-300",
    status: "PAID",
    customer: {
      id: "C-3",
      location: { city: "Hồ Chí Minh", district: "Quận 1" }
    },
    items: [
      {
        sku: "BK-01", qty: 1, price: 120000,
        tags: ["book"],
        allocations: [{ warehouse: "HN", qty: 1 }]
      },
      {
        sku: "PN-02", qty: 3, price: 10000,
        tags: ["office"],
        allocations: [{ warehouse: "SG", qty: 3 }]
      }
    ],
    createdAt: ISODate("2026-11-04T06:00:00Z")
  },
  {
    _id: "O-400",
    status: "DRAFT",
    customer: {
      id: "C-4",
      location: { city: "Hà Nội", district: "Cầu Giấy" }
    },
    items: [],
    createdAt: ISODate("2026-11-05T07:00:00Z")
  }
]

for (const order of sampleOrders) {
  lab.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  )
}

lab.orders.find({}, { _id: 1, status: 1, "items.sku": 1 })
~~~

Đây là tập dữ liệu minh họa; mỗi `sku` xuất hiện tối đa một lần trong từng order **theo mẫu này**, nhưng MongoDB không tự đảm bảo quy tắc ấy. Nếu ứng dụng cho phép nhiều line item có cùng SKU, khi cập nhật cần lựa chọn rõ cập nhật một hay tất cả các phần tử khớp.

## 3. Truy vấn field của embedded document bằng dot notation

Khi đường dẫn chỉ đi qua các **object** lồng nhau, dùng dấu chấm để xác định field:

~~~javascript
// Đơn có khách hàng ở Hà Nội.
lab.orders.find(
  { "customer.location.city": "Hà Nội" },
  { _id: 1, "customer.location.city": 1 }
)
// Dữ liệu mẫu: O-100, O-400.
~~~

Cú pháp này có nghĩa: đi vào `customer`, đi tiếp `location`, rồi so sánh `city`. Dấu chấm nằm trong **tên field của filter**, vì vậy phải đặt đường dẫn trong dấu nháy kép hoặc đơn:

~~~javascript
// Đúng:
{ "customer.location.city": "Hà Nội" }

// Sai cú pháp JavaScript:
// { customer.location.city: "Hà Nội" }
~~~

### 3.1. So sánh cả embedded document có tính đến thứ tự field

Ví dụ:

~~~javascript
// Chỉ hợp lý nếu object được lưu với đúng các field,
// giá trị và thứ tự tương ứng:
lab.orders.find({
  "customer.location": {
    city: "Hà Nội",
    district: "Ba Đình"
  }
})
~~~

Với **equality trên một embedded document nguyên khối**, MongoDB xét cả **thứ tự field** và cấu trúc của document. Nếu object lưu `district` trước `city`, hoặc có field bổ sung, phép so sánh nguyên object có thể không khớp. Khi chỉ quan tâm một hoặc vài thuộc tính, **dot notation** thường rõ hơn:

~~~javascript
lab.orders.find({
  "customer.location.city": "Hà Nội",
  "customer.location.district": "Ba Đình"
})
~~~

Hai điều kiện trên đi qua object `customer.location` (không phải array), nên chúng cùng mô tả một embedded location trong document. Sự khác biệt **cùng object / khác phần tử** trở nên quan trọng khi đường dẫn đi qua một array.

### 3.2. Kiểm tra field tồn tại và kiểu dữ liệu

~~~javascript
// Có field city ở đường dẫn này.
lab.orders.find({
  "customer.location.city": { $exists: true }
})

// City phải là string.
lab.orders.find({
  "customer.location.city": { $type: "string" }
})

// City chứa 'Hà' (regex minh họa).
lab.orders.find({
  "customer.location.city": { $regex: "Hà" }
})
~~~

`$exists: true` không đòi field khác null; nó chỉ kiểm tra sự hiện diện. `$type` hữu ích khi schema linh hoạt có dữ liệu không nhất quán giữa các document.

## 4. Dot notation đi qua mảng các document

Giả sử muốn tìm những order có **ít nhất một item mang SKU `BK-01`**:

~~~javascript
lab.orders.find(
  { "items.sku": "BK-01" },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

Vì `items` là một array of documents, đường dẫn `"items.sku"` có thể đi vào **bất cứ phần tử nào** của mảng và khớp khi tìm được `sku` thích hợp. Nó **không yêu cầu** item đó nằm ở phần tử đầu tiên.

Những phép so sánh khác cũng hoạt động tương tự:

~~~javascript
// Có ít nhất một item qty >= 3.
lab.orders.find(
  { "items.qty": { $gte: 3 } },
  { _id: 1 }
)
// O-100, O-200, O-300.

// Có ít nhất một item màu xanh.
lab.orders.find(
  { "items.attributes.color": "blue" },
  { _id: 1 }
)
// O-100, O-200.

// Ít nhất một item có tag 'gift'.
lab.orders.find(
  { "items.tags": "gift" },
  { _id: 1 }
)
// O-100.
~~~

### 4.1. Điểm dễ sai nhất: các điều kiện có thể khớp **khác phần tử**

Xét filter:

~~~javascript
lab.orders.find(
  {
    "items.sku": "BK-01",
    "items.qty": { $gte: 3 }
  },
  { _id: 1 }
)
~~~

Kết quả của dữ liệu mẫu là **`O-100`, `O-200` và `O-300`**.

Tại sao `O-100` vẫn khớp dù item `BK-01` có `qty: 1`?

~~~text
O-100.items
  [0] { sku: "BK-01", qty: 1 }  -> đáp ứng sku = BK-01
  [1] { sku: "PN-02", qty: 3 }  -> đáp ứng qty >= 3
  [2] { sku: "BK-03", qty: 4 }  -> cũng đáp ứng qty >= 3
~~~

MongoDB hiểu hai predicate dot notation là: **document chứa item nào đó có SKU BK-01** *và* **document chứa item nào đó có số lượng ít nhất 3**. Nó **không mặc nhiên đòi hai predicate khớp trên cùng một item**.

Đây không phải lỗi MongoDB; đó là ngữ nghĩa truy vấn đã được định nghĩa. Nếu nghiệp vụ yêu cầu **cùng một phần tử**, hãy dùng `$elemMatch`.

## 5. `$elemMatch`: buộc nhiều điều kiện lên cùng phần tử

Query operator **`$elemMatch`** chọn các document có **ít nhất một phần tử trong array** thỏa **tất cả điều kiện đặt bên trong**.

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        qty: { $gte: 3 }
      }
    }
  },
  { _id: 1 }
)
// Chỉ O-200.
~~~

Đọc câu truy vấn thành: “Tìm order mà **tồn tại một phần tử `items[i]`** có `sku = BK-01` **và** `qty >= 3`”.

~~~text
O-100: BK-01 qty 1, PN-02 qty 3, BK-03 qty 4 -> KHÔNG
O-200: BK-01 qty 3                            -> CÓ
O-300: BK-01 qty 1, PN-02 qty 3               -> KHÔNG
O-400: items = []                              -> KHÔNG
~~~

### 5.1. So sánh dot notation và `$elemMatch`

| Filter | Diễn giải | Kết quả mẫu |
|---|---|---|
| `{"items.sku": "BK-01"}` | Có ít nhất một phần tử có SKU BK-01. | O-100, O-200, O-300 |
| `{"items.qty": {$gte: 3}}` | Có ít nhất một phần tử có qty >= 3. | O-100, O-200, O-300 |
| Hai điều kiện dot notation riêng | Một phần tử có SKU đúng **và có thể phần tử khác** có qty >= 3. | O-100, O-200, O-300 |
| `{items: {$elemMatch: {sku:"BK-01",qty:{$gte:3}}}}` | **Cùng một** item phải thỏa cả hai. | **O-200** |
| `{"items.0.sku": "BK-01"}` | Phần tử đầu tiên có SKU BK-01. | O-100, O-200, O-300 |

Quy tắc thực hành: **khi có từ hai predicate trở lên mô tả “cùng một phần tử của array”, hãy cân nhắc `$elemMatch` ngay từ lúc thiết kế filter.**

### 5.2. `$elemMatch` trên array of scalars

Với mảng số:

~~~javascript
db.getSiblingDB("array_query_lab").scores.insertOne({
  _id: "S-1",
  points: [72, 95]
})

// Hai điều kiện có thể khớp ở hai phần tử khác nhau:
db.getSiblingDB("array_query_lab").scores.find({
  points: { $gte: 80, $lt: 90 }
})
// S-1 có thể khớp: 95 >= 80 và 72 < 90.

// Cùng một phần tử phải nằm trong [80, 90):
db.getSiblingDB("array_query_lab").scores.find({
  points: {
    $elemMatch: { $gte: 80, $lt: 90 }
  }
})
// S-1 không khớp vì không có điểm nào từ 80 đến dưới 90.
~~~

Ví dụ này cho thấy `$elemMatch` hữu ích không chỉ với subdocuments mà còn với **nhiều điều kiện lên một phần tử số**. Với **một điều kiện** như `"items.sku": "BK-01"`, không nhất thiết phải dùng `$elemMatch`.

### 5.3. `$elemMatch` và document không phải array

Một document có `items` bị lưu nhầm thành object:

~~~javascript
{
  _id: "BAD-SHAPE",
  items: { sku: "BK-01", qty: 3 }
}
~~~

Filter dot notation `{"items.sku":"BK-01"}` có thể khớp cả **object** lẫn **phần tử trong array**, vì nó truy vấn đường dẫn. Trong khi đó, `{items: {$elemMatch: {sku:"BK-01", qty:{$gte:3}}}}` yêu cầu `items` là array có phần tử tương ứng, nên **không khớp object đơn** như trên.

Khi schema linh hoạt hoặc có dữ liệu di sản, cần kiểm tra **kiểu dữ liệu** nếu ứng dụng thực sự yêu cầu array:

~~~javascript
lab.orders.find({
  items: { $type: "array" }
})
~~~

## 6. `$elemMatch` cho field lồng bên trong một item

Điều kiện đặt trong `$elemMatch` có thể tiếp tục truy cập **embedded document bên trong mỗi phần tử**. Ví dụ muốn item `BK-01` có màu xanh:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        "attributes.color": "blue"
      }
    }
  },
  { _id: 1 }
)
// O-100 và O-200.
~~~

Ở đây `attributes` là object thuộc **một item** đang được chọn bởi `$elemMatch`; dot notation `"attributes.color"` đi từ item đó vào object con, không thể nhảy sang item khác.

Một ví dụ thêm điều kiện trạng thái order ở ngoài:

~~~javascript
lab.orders.find(
  {
    status: "PAID",
    items: {
      $elemMatch: {
        sku: "BK-01",
        "attributes.color": "blue"
      }
    }
  },
  { _id: 1 }
)
// O-100.
~~~

`status` thuộc document cha nên đặt ngoài `$elemMatch`. Nếu vô tình đặt `status` bên trong, MongoDB sẽ tìm field `status` **trong từng item**, không phải `orders.status`.

## 7. Mảng lồng nhiều cấp: cần giữ đúng từng ranh giới phần tử

Mỗi item có mảng `allocations` gồm nhiều document phân bổ kho. Đường dẫn:

~~~text
orders.items[].allocations[].warehouse
       ^       ^
       |       +-- array thứ hai
       +---------- array thứ nhất
~~~

### 7.1. Dot notation xuyên hai array

~~~javascript
lab.orders.find(
  { "items.allocations.warehouse": "SG" },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

Ý nghĩa: có **một allocation** nào đó trong **một item** nào đó có `warehouse = "SG"`. Nếu thêm `"items.allocations.qty": {$gte:2}` thành predicate riêng, điều kiện `warehouse` và `qty` vẫn có thể được thỏa bởi **hai allocations khác nhau**, thậm chí thuộc **hai items khác nhau**.

### 7.2. Chỉ một `$elemMatch` ở cấp items chưa đủ

Xem item đầu của `O-200`:

~~~javascript
{
  sku: "BK-01",
  qty: 3,
  allocations: [
    { warehouse: "SG", qty: 1 },
    { warehouse: "HN", qty: 2 }
  ]
}
~~~

Filter sau **khớp `O-200`**:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        "allocations.warehouse": "SG",
        "allocations.qty": { $gte: 2 }
      }
    }
  },
  { _id: 1 }
)
~~~

Vì `$elemMatch` ở đây mới bảo đảm **cùng item BK-01**; bên trong item đó, điều kiện `allocations.warehouse = SG` khớp allocation thứ nhất, còn `allocations.qty >= 2` khớp allocation thứ hai.

Để yêu cầu **cùng một allocation**, dùng **`$elemMatch` lồng nhau**:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        allocations: {
          $elemMatch: {
            warehouse: "SG",
            qty: { $gte: 2 }
          }
        }
      }
    }
  },
  { _id: 1 }
)
// Không có order nào trong bộ mẫu khớp.
~~~

Đổi warehouse thành `HN`:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "BK-01",
        allocations: {
          $elemMatch: {
            warehouse: "HN",
            qty: { $gte: 2 }
          }
        }
      }
    }
  },
  { _id: 1 }
)
// O-200.
~~~

Đọc câu điều kiện thành:

> Tồn tại một **item** có `sku = "BK-01"`, và trong **chính item đó** tồn tại một **allocation** có `warehouse = "HN"` và `qty >= 2`.

Đây là quy tắc tổng quát cho các cấu trúc kiểu **`orders[].lines[].allocations[]`**: mỗi ranh giới array mà nghiệp vụ yêu cầu tính đồng nhất phần tử cần được thể hiện trong filter.

### 7.3. Có nhiều object lồng nhưng chỉ một array

Không phải mỗi dấu chấm đều cần `$elemMatch`. Ví dụ `items[].attributes.color` chỉ đi qua **một array `items`**, còn `attributes` là object bình thường. Khi kiểm tra cùng item:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      "attributes.color": "blue"
    }
  }
}
~~~

Không cần `$elemMatch` riêng cho `attributes` vì nó không phải array.

## 8. Các toán tử hữu ích khi truy vấn mảng document

### 8.1. `$in`: một field thỏa một trong nhiều giá trị

Tìm order có **ít nhất một item** mang một trong các SKU được chọn:

~~~javascript
lab.orders.find(
  { "items.sku": { $in: ["BK-01", "BK-03"] } },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

`$in` ở đây tương đương một điều kiện "SKU thuộc tập", **không yêu cầu** order chứa **cả hai** SKU. Muốn chứa cả hai SKU ở các item bất kỳ, có thể dùng `$all` trên đường dẫn giá trị:

~~~javascript
lab.orders.find(
  { "items.sku": { $all: ["BK-01", "BK-03"] } },
  { _id: 1 }
)
// O-100 có cả BK-01 và BK-03.
~~~

Phân biệt:

- **`$in`**: ít nhất một giá trị trùng một phần tử của tập yêu cầu.
- **`$all`**: tất cả giá trị được liệt kê phải có trong giá trị mảng tại đường dẫn phù hợp.
- **`$elemMatch`**: nhiều điều kiện phải khớp **trên cùng một phần tử mảng**.

Khi kết hợp nhiều điều kiện phức tạp, phải chọn operator theo **ngữ nghĩa nghiệp vụ**, không chỉ theo số lượng điều kiện.

### 8.2. `$all` với mảng nằm bên trong từng item

Tìm order có một item được gắn **cả hai nhãn "book" và "gift"**:

~~~javascript
lab.orders.find(
  {
    items: {
      $elemMatch: {
        tags: { $all: ["book", "gift"] }
      }
    }
  },
  { _id: 1 }
)
// O-100: item BK-03 có tags ["book", "gift"].
~~~

Ở đây `$elemMatch` đảm bảo ta đang xem **một item**, và `$all` đảm bảo **mảng tags của chính item đó** chứa đủ hai nhãn. Nếu chỉ viết hai predicate trên đường dẫn `items.tags` ở cấp order, cần hết sức cẩn thận vì điều kiện trên array có thể được thỏa qua các phần tử khác nhau.

Nếu nghiệp vụ là “một order có cả item SKU A và item SKU B”, hai item **không bắt buộc là cùng phần tử**. Khi đó có thể dùng hai điều kiện `$elemMatch` trong `$all` trên mảng document:

~~~javascript
lab.orders.find({
  items: {
    $all: [
      { $elemMatch: { sku: "BK-01", qty: { $gte: 1 } } },
      { $elemMatch: { sku: "BK-03", qty: { $gte: 1 } } }
    ]
  }
})
// O-100.
~~~

Mỗi `$elemMatch` mô tả một yêu cầu cho **một item**. Hai yêu cầu có thể được đáp ứng bởi **hai item khác nhau**, đúng với bài toán “order chứa cả hai sản phẩm”.

### 8.3. `$size` và mảng rỗng

~~~javascript
// Order chưa có item nào.
lab.orders.find(
  { items: { $size: 0 } },
  { _id: 1 }
)
// O-400.

// Order có đúng hai item.
lab.orders.find(
  { items: { $size: 2 } },
  { _id: 1 }
)
// O-200, O-300.
~~~

`$size` so sánh **độ dài array** bằng một số nguyên cụ thể. Không viết `{items:{$size:{$gte:2}}}` để tìm array có ít nhất hai phần tử; `$size` không nhận một range query như vậy. Với nhu cầu “có ít nhất N phần tử”, có thể xét đường dẫn chỉ số:

~~~javascript
// Có phần tử thứ 3 (chỉ số 2), tức ít nhất ba phần tử.
lab.orders.find({
  "items.2": { $exists: true }
})
// O-100.
~~~

Đây là một mẹo truy vấn khi array đúng kiểu và có thứ tự vị trí, không phải cơ chế kiểm chứng ràng buộc cardinality của schema. `$size` không tự dùng multikey index để tối ưu phần kiểm tra kích thước; hãy kiểm tra `explain()` nếu query chạy thường xuyên.

### 8.4. `$exists` trên đường dẫn mảng lồng

~~~javascript
// Có ít nhất một item với field attributes.color.
lab.orders.find(
  { "items.attributes.color": { $exists: true } },
  { _id: 1 }
)
// O-100, O-200.

// items tồn tại, kể cả khi là array rỗng.
lab.orders.find(
  { items: { $exists: true } },
  { _id: 1 }
)
// Trong bộ mẫu: cả bốn order.
~~~

Field **tồn tại** không đồng nghĩa **có giá trị khác null**. Một array rỗng vẫn là một field có tồn tại. Muốn phân biệt:

| Filter | Điều muốn hỏi |
|---|---|
| `{items: {$exists: false}}` | Không có field `items`. |
| `{items: {$size: 0}}` | `items` là array có 0 phần tử. |
| `{"items.0": {$exists: true}}` | Có phần tử ở chỉ số 0 (array có ít nhất một phần tử). |
| `{items: {$type: "array"}}` | `items` có kiểu BSON array. |
| `{"items.price": {$type: "number"}}` | Có giá trị số tại đường dẫn giá trong phần tử. |

Với schema thực tế có dữ liệu cũ, có thể cần kết hợp `$type` với những điều kiện khác để tránh coi object đơn là array.

### 8.5. Null, field thiếu và `$ne`

MongoDB có ngữ nghĩa đặc biệt với `null`. Ví dụ:

~~~javascript
lab.orders.find({
  "items.attributes.color": null
})
~~~

Điều kiện equality với `null` có thể khớp khi đường dẫn không tồn tại **hoặc** có giá trị null; qua array nhiều cấp, sự thiếu field của các phần tử khiến cách diễn giải càng dễ sai. Không dùng điều kiện `= null` như một cách chắc chắn để nói rằng **mọi item đều có color null**.

Nếu muốn “tồn tại item có color là chuỗi”, hãy viết rõ:

~~~javascript
lab.orders.find({
  "items.attributes.color": { $type: "string" }
})
~~~

Một bẫy khác:

~~~javascript
lab.orders.find({
  "items.sku": { $ne: "BK-01" }
})
// Trong bộ mẫu: O-400 (không có item BK-01).
~~~

`$ne` trên đường dẫn array ở đây mang ý nghĩa **không có giá trị BK-01 phù hợp tại đường dẫn**, kể cả khi đường dẫn thiếu. Nó **không** có nghĩa “có ít nhất một item có SKU khác BK-01”. Một order vừa có BK-01 vừa có PN-02 **không** được chọn chỉ vì PN-02 khác BK-01.

Muốn hỏi **tồn tại item khác SKU BK-01**, viết rõ operator tồn tại phần tử:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: { sku: { $ne: "BK-01" } }
  }
})
// O-100, O-200, O-300 vì có item khác BK-01.
~~~

Với field có thể vắng mặt, `$ne` bên trong `$elemMatch` cũng có thể khớp phần tử thiếu `sku`. Nếu muốn **SKU tồn tại và khác**, thêm `sku: {$exists:true, $ne:"BK-01"}` trong cùng predicate. Cú pháp sau minh họa rõ điều đó:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: { $exists: true, $ne: "BK-01" }
    }
  }
})
~~~

Nếu nghiệp vụ là “**không tồn tại bất kỳ item nào** có SKU BK-01”, có thể dùng:

~~~javascript
lab.orders.find({
  items: {
    $not: { $elemMatch: { sku: "BK-01" } }
  }
})
// O-400.
~~~

Điều kiện phủ định có thể khớp cả document **không có field items**. Nếu yêu cầu chắc chắn `items` là array, thêm điều kiện kiểu dữ liệu. Phủ định một mệnh đề tồn tại và tồn tại một phần tử phủ định là **hai bài toán khác nhau**.

## 9. Truy vấn theo chỉ số vị trí trong mảng

Array trong MongoDB có thứ tự. Dùng **chỉ số bắt đầu từ 0** trong dot notation:

~~~javascript
// SKU của phần tử đầu tiên là BK-01.
lab.orders.find(
  { "items.0.sku": "BK-01" },
  { _id: 1 }
)
// O-100, O-200, O-300.

// Phần tử thứ hai có qty >= 3.
lab.orders.find(
  { "items.1.qty": { $gte: 3 } },
  { _id: 1 }
)
// O-100 và O-300.
~~~

Phân biệt:

- `"items.sku": "BK-01"` — **bất kỳ** item nào.
- `"items.0.sku": "BK-01"` — **chỉ item đầu tiên**.
- `items: {$elemMatch:{...}}` — **bất kỳ một item**, nhưng các điều kiện bên trong phải áp lên **cùng item**.

Truy vấn theo chỉ số hợp lý khi vị trí có ý nghĩa nghiệp vụ ổn định, ví dụ phân biệt “mốc đầu tiên” trong một chuỗi có thứ tự. Nhưng với giỏ hàng hoặc danh sách line items, thứ tự có thể thay đổi do thêm/xóa/sắp xếp; dùng chỉ số cứng thường mong manh hơn truy vấn theo **định danh item**.

### 9.1. Phần tử tại vị trí không tồn tại

Nếu array chỉ có một phần tử, `"items.1"` không tồn tại. Một query `"items.1.qty": {$exists: true}` không khớp. Điều này khác trường hợp item thứ hai tồn tại nhưng `qty` bị thiếu. Hãy dùng `"items.1": {$exists: true}` để hỏi về chính phần tử đó, hoặc `"items.1.qty": {$exists: true}` để hỏi field bên trong.

### 9.2. Truy vấn bằng index khác thao tác projection/sửa index

Trong filter `"items.0.sku"`, số `0` là một phần của **đường dẫn truy vấn**. Trong update `"items.$.status"`, ký hiệu `$` là **positional update operator** được quyết định bởi match. Trong projection `"items.$"`, `$` lại là **positional projection operator**. Chúng có các điều kiện sử dụng riêng và không thể tráo vị trí cho nhau.

## 10. Filter document cha khác với projection phần tử mảng

Một điểm quan trọng: truy vấn sau chọn các **order** có SKU BK-01, nhưng mặc định MongoDB trả về **toàn bộ array `items`** của order được chọn:

~~~javascript
lab.orders.find({
  "items.sku": "BK-01"
})
~~~

Filter kiểm tra **document có đủ điều kiện được trả về hay không**; nó không tự loại những phần tử trong array không đáp ứng filter. Muốn chỉ trả về field hoặc phần tử liên quan, phải dùng **projection** hoặc **aggregation**.

### 10.1. Projection đường dẫn field

~~~javascript
lab.orders.find(
  { status: "PAID" },
  {
    _id: 1,
    status: 1,
    "items.sku": 1
  }
)
~~~

MongoDB giữ cấu trúc `items` phù hợp, nhưng chỉ hiển thị `sku` trong mỗi phần tử thay vì toàn bộ `qty`, `price`, `tags`. Projection này **không lọc bớt item**; nó chỉ giới hạn **field** được trả về.

### 10.2. `$elemMatch` ở vị trí projection

MongoDB có cả **query `$elemMatch`** và **projection `$elemMatch`**. Chúng ở hai vị trí khác nhau trong `find(filter, projection)`:

~~~javascript
lab.orders.find(
  { _id: "O-100" },
  {
    _id: 1,
    status: 1,
    items: {
      $elemMatch: {
        sku: "BK-01"
      }
    }
  }
)
~~~

Projection `$elemMatch` chỉ trả **phần tử đầu tiên của array** thỏa điều kiện projection, đặt trong một array (nếu có phần tử phù hợp). Nó **không trả tất cả phần tử khớp**. Với `O-100`, array `items` được trả về chỉ chứa item BK-01; filter `{_id:"O-100"}` vẫn chỉ là điều kiện chọn order.

Điều kiện trong **query** và điều kiện trong **projection** cũng có thể khác nhau. Cẩn thận khi dùng điều kiện filter và projection không cùng ý nghĩa: document có thể được chọn vì một phần tử, nhưng projection trả phần tử khác hoặc không trả field đó.

### 10.3. Positional projection `$`

Khi filter chọn document qua một điều kiện trên array, có thể dùng positional projection để lấy phần tử khớp đầu tiên:

~~~javascript
lab.orders.find(
  { "items.sku": "BK-01" },
  {
    _id: 1,
    "items.$": 1
  }
)
~~~

`"items.$": 1` trả **phần tử đầu tiên được chọn theo điều kiện mảng trong query**. Positional projection có giới hạn về số array fields, hình dạng query và vị trí operator; khi cần điều kiện phức tạp trên nhiều arrays, ưu tiên **aggregation `$filter`** để diễn đạt rõ phần tử được trả về.

### 10.4. `$slice` trong projection

Nếu chỉ cần N phần tử đầu để giới hạn dữ liệu trả về:

~~~javascript
lab.orders.find(
  { _id: "O-100" },
  {
    _id: 1,
    items: { $slice: 2 }
  }
)
// Chỉ lấy hai item đầu; không phải chọn theo điều kiện SKU/qty.
~~~

`$slice` trong projection lấy một đoạn array theo **vị trí**, khác với `$elemMatch` (theo điều kiện). Không dùng nó như một phép lọc nghiệp vụ nếu yêu cầu là “lấy hai item có qty cao nhất”; trường hợp đó cần sort/aggregation phù hợp.

## 11. Lọc tất cả phần tử bằng aggregation `$filter`

Nếu muốn trả về **tất cả items** đáp ứng điều kiện (thay vì phần tử đầu tiên), aggregation operator **`$filter`** giúp xử lý nội dung array trong document được trả về.

Ví dụ: với mọi order được xét, chỉ giữ items có SKU BK-01 và qty >= 3:

~~~javascript
lab.orders.aggregate([
  {
    $match: {
      status: { $in: ["PAID", "NEW"] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      matchingItems: {
        $filter: {
          input: "$items",
          as: "line",
          cond: {
            $and: [
              { $eq: ["$$line.sku", "BK-01"] },
              { $gte: ["$$line.qty", 3] }
            ]
          }
        }
      }
    }
  },
  {
    $match: {
      "matchingItems.0": { $exists: true }
    }
  }
])
// O-200 với matchingItems chứa item BK-01 qty=3.
~~~

Ở đây:

- **`$match`** là một *pipeline stage*, dùng để chọn order.
- **`$project`** là *pipeline stage*, xác định hình dạng output.
- **`$filter`** là một *aggregation expression*, xử lý mảng `items` và giữ những phần tử thỏa điều kiện.
- **`$$line`** là biến đại diện **một phần tử** trong array đang được xét, nhờ `as: "line"`.
- `$match` cuối loại các order không có phần tử nào được `$filter` giữ lại.

`$filter` sẽ giữ **tất cả** phần tử phù hợp và giữ thứ tự tương đối của chúng trong array. Không nhầm `$filter` với `$elemMatch` projection, vốn chỉ chọn phần tử đầu tiên. MongoDB có thêm toán tử `$map` để biến đổi từng phần tử và `$reduce` để tổng hợp một array theo accumulator; hãy chọn theo kiểu output mong muốn.

### 11.1. Chỉ lấy subset item nhưng vẫn giữ một phần field của order

~~~javascript
lab.orders.aggregate([
  { $match: { _id: "O-100" } },
  {
    $project: {
      status: 1,
      createdAt: 1,
      bookItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $in: ["$$item.sku", ["BK-01", "BK-03"]]
          }
        }
      }
    }
  }
])
~~~

Output của `O-100` chứa `bookItems` gồm BK-01 và BK-03, giữ lại `status` và `createdAt`. Đây là **output tính toán từ truy vấn**, không sửa `items` trong collection.

### 11.2. `$unwind`: biến mỗi phần tử thành một dòng trong pipeline

Để tạo báo cáo số lượng bán theo SKU, dùng `$unwind`:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQty: { $sum: "$items.qty" },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { totalQty: -1 } }
])
~~~

Mỗi order PAID có 3 items có thể trở thành 3 pipeline documents sau `$unwind`. Khi ấy `items.sku` và `items.qty` nói đến **cùng một item đã được tách thành dòng hiện tại**. `$group` sau đó cộng số lượng theo SKU.

Trong ví dụ, `orderCount: {$sum:1}` đếm **số dòng item** sau unwind, **không nhất thiết là số order duy nhất** nếu một order có nhiều dòng trùng SKU. Muốn đếm số order duy nhất cần thiết kế phép tổng hợp riêng (ví dụ nhóm theo cặp order/SKU trước).

Với array rỗng như `O-400`, `$unwind: "$items"` mặc định **không tạo dòng output**. Nếu cần giữ document có array rỗng/missing, dùng dạng object có `preserveNullAndEmptyArrays: true` và xử lý điều kiện tiếp theo thích hợp.

### 11.3. Khi nào dùng `find`, khi nào dùng aggregation?

| Nhu cầu | Cách thường phù hợp |
|---|---|
| Lọc order có một item thỏa điều kiện | `find` + `$elemMatch` query. |
| Trả tất cả items như document gốc | `find`, projection field nếu cần. |
| Chỉ trả item đầu tiên thỏa điều kiện | `$elemMatch` projection / positional projection khi phù hợp. |
| Trả **tất cả items** thỏa điều kiện | Aggregation `$filter`. |
| Chuyển từng item thành dòng để group/sort | Aggregation `$unwind`. |
| Tính lại field dựa trên items | Aggregation `$map`, `$reduce`, `$sum` hoặc stage liên quan. |

Không cần dựng pipeline dài cho một filter đơn giản. Ngược lại, đừng cố ép một projection `$elemMatch` thành phép lọc **mọi** phần tử vì ý nghĩa của nó không đáp ứng yêu cầu đó.

## 12. Từ truy vấn tới cập nhật phần tử mảng

Query operator `$elemMatch` **chỉ giúp chọn document**. Nếu muốn cập nhật đúng một hoặc nhiều phần tử bên trong array, phần đường dẫn trong **update document** phải dùng các positional update operators phù hợp. Đây là hai vấn đề liên quan nhưng **không đồng nhất**:

~~~text
Filter:
  document nào đủ điều kiện để chạy update?

Update path:
  phần tử array nào trong document đó sẽ được sửa?
~~~

### 12.1. Positional operator `$`: phần tử khớp đầu tiên

Muốn đánh dấu item BK-01 trong order O-100:

~~~javascript
lab.orders.updateOne(
  {
    _id: "O-100",
    "items.sku": "BK-01"
  },
  {
    $set: {
      "items.$.picked": true
    }
  }
)
~~~

`items.$` đại diện cho **phần tử đầu tiên của array `items` được match theo filter**. Đường dẫn không được đặt dấu `$` tùy tiện nếu filter không xác định array element một cách phù hợp. Operator này có giới hạn khi query chứa nhiều array fields hoặc đi qua nhiều mảng lồng; cách xác định phần tử có thể trở nên mơ hồ.

Nếu một order có hai item cùng SKU và bạn muốn sửa **cả hai**, positional `$` không đáp ứng yêu cầu vì nó chọn phần tử đầu tiên; nên dùng `$[identifier]`.

### 12.2. Filtered positional operator `$[identifier]`: mọi phần tử khớp `arrayFilters`

~~~javascript
lab.orders.updateOne(
  { _id: "O-100" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BK-01" }
    ]
  }
)
~~~

`$[line]` đại diện cho **mọi phần tử của `items`** thỏa điều kiện trên biến `line` trong `arrayFilters`. Cú pháp tổng quát:

~~~javascript
db.collection.updateOne(
  { /* filter để chọn document cha */ },
  {
    $set: {
      "arrayField.$[element].someField": someValue
    }
  },
  {
    arrayFilters: [
      { "element.someCondition": expectedValue }
    ]
  }
)
~~~

Tên `element`/`line` là định danh do bạn đặt, phải tuân thủ cú pháp tên identifier của MongoDB. `arrayFilters` là **option của update**, không phải một field tùy ý bên trong document. Nếu có nhiều phần tử trùng SKU, tất cả phần tử thỏa filter đều được sửa.

Ví dụ tăng `qty` của các dòng BK-01 nếu còn hạn mức:

~~~javascript
lab.orders.updateOne(
  { _id: "O-200" },
  { $inc: { "items.$[line].qty": 1 } },
  {
    arrayFilters: [
      {
        "line.sku": "BK-01",
        "line.qty": { $lt: 5 }
      }
    ]
  }
)
~~~

Các điều kiện `line.sku` và `line.qty` trong **cùng một arrayFilters entry** mô tả cùng phần tử `line`; đó là logic tương tự việc yêu cầu cùng phần tử ở truy vấn `$elemMatch`. Sau thao tác, số lượng và giá trị summary/total của order nếu có **không tự động** được cập nhật; ứng dụng phải duy trì bất biến liên quan một cách nguyên tử khi cần.

### 12.3. All positional operator `$[]`: sửa tất cả phần tử

~~~javascript
lab.orders.updateOne(
  { _id: "O-100" },
  {
    $set: {
      "items.$[].inspected": false
    }
  }
)
~~~

`$[]` áp dụng lên **mọi phần tử** của `items` trong document được chọn. Với một array rỗng, không có phần tử nào để sửa. Không dùng `$[]` nếu nghiệp vụ chỉ muốn sửa các item thuộc một SKU; nó có thể cập nhật nhiều dữ liệu hơn dự định.

### 12.4. Hai cấp mảng trong `arrayFilters`

Khi muốn sửa allocation `warehouse = "HN"` của **chính item BK-01**, dùng hai identifier:

~~~javascript
lab.orders.updateOne(
  { _id: "O-200" },
  {
    $inc: {
      "items.$[line].allocations.$[allocation].qty": 1
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BK-01" },
      { "allocation.warehouse": "HN" }
    ]
  }
)
~~~

Trong bộ mẫu, lệnh tăng số lượng allocation HN của item BK-01 trong order O-200. `line` chọn các item phù hợp; `allocation` chọn các allocations trong **những item đã chọn**. Nếu có nhiều allocations HN dưới cùng một item, tất cả phần tử khớp được cập nhật.

Đây là trường hợp điển hình mà cách kết hợp `$[line]` và `$[allocation]` rõ ràng hơn positional `$`, vốn có các giới hạn khi đường dẫn đi qua nhiều arrays.

**Lưu ý:** Các thao tác positional update có giới hạn cú pháp riêng cho **upsert** khi document chưa tồn tại; ví dụ một số update dùng `$[]`/`$[identifier]` yêu cầu query có equality match chính xác trên array nếu upsert tạo document. Không lấy ví dụ cập nhật document đã tồn tại rồi mặc nhiên áp dụng cùng cấu trúc cho upsert.

### 12.5. `$pull`: xóa phần tử theo điều kiện

Muốn bỏ tất cả dòng có SKU PN-02 khỏi một order:

~~~javascript
lab.orders.updateOne(
  { _id: "O-300" },
  {
    $pull: {
      items: { sku: "PN-02" }
    }
  }
)
~~~

`$pull` xóa **mọi phần tử phù hợp** với điều kiện trong array, không chỉ phần tử đầu tiên. Một khi xóa line item, cần cân nhắc lại `total`, tồn kho hoặc các quy tắc nghiệp vụ khác; chỉ sửa array không mặc nhiên làm những giá trị tổng hợp liên quan đúng theo mọi domain.

### 12.6. Cẩn thận với tính nguyên tử và cạnh tranh cập nhật

Một lệnh update trên **một document** là nguyên tử, kể cả khi sửa nhiều trường/array elements bên trong document đó. Nhưng:

- Hai client cùng đọc một array rồi `$set` **toàn bộ array** bằng bản sao cũ có thể gây **lost update** ở logic ứng dụng.
- Cập nhật một phần tử có thể làm chỉ số vị trí của các phần tử khác thay đổi sau `$pull`/`$push`; không giữ chỉ số index như ID bền vững.
- Nên dùng **định danh ổn định của phần tử**, ví dụ `lineId`, nếu hai item có thể cùng SKU hoặc thứ tự thay đổi.
- Với quy tắc yêu cầu “cập nhật giá trị nếu còn ở version cũ”, đưa **điều kiện so sánh** vào filter/arrayFilters khi phù hợp.
- Ghi nhiều document độc lập cần transaction hoặc workflow nhất quán tương ứng; atomicity của một document không lan sang document khác.

## 13. Index cho đường dẫn trong mảng document

MongoDB hỗ trợ **multikey index** khi một indexed field chứa array. Nếu tạo index trên `items.sku`, MongoDB quản lý các index keys tương ứng với giá trị từ các phần tử mảng:

~~~javascript
lab.orders.createIndex({
  "items.sku": 1
})
~~~

Index này có thể giúp truy vấn:

~~~javascript
lab.orders.find({
  "items.sku": "BK-01"
})
~~~

Nhưng **có index** không đồng nghĩa mọi truy vấn liên quan array sẽ nhanh; query planner còn xem tính chọn lọc, số documents/index entries, sort, projection và kích thước dữ liệu.

### 13.1. Compound multikey index và `$elemMatch`

Với truy vấn thường xuyên tìm item theo SKU và ngưỡng số lượng:

~~~javascript
lab.orders.createIndex({
  "items.sku": 1,
  "items.qty": 1
})
~~~

Hai field cùng thuộc **mảng `items` chứa subdocuments**, nên đây là trường hợp có thể áp dụng compound multikey index. Khi nhiều predicate trên cùng array phải khớp **cùng một item**, `$elemMatch` giúp MongoDB hiểu quan hệ đó và có thể **compound index bounds** phù hợp:

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
})
~~~

Nếu viết hai điều kiện dot notation riêng:

~~~javascript
lab.orders.find({
  "items.sku": "BK-01",
  "items.qty": { $gte: 3 }
})
~~~

thì **ngữ nghĩa đã khác** (có thể khớp hai item khác nhau). Vì thế engine không thể tự áp dụng điều kiện “cùng phần tử” chỉ vì đã có compound index. Ngoài tính đúng đắn, `$elemMatch` cũng có thể ảnh hưởng cách compound bounds được dùng. Hãy dùng `explain()` để so sánh trên dữ liệu thực, thay vì suy ra mức tối ưu chỉ từ index definition.

### 13.2. Giới hạn của compound multikey index

MongoDB có giới hạn đối với **parallel arrays**: không thể tùy ý tạo compound multikey index khi nhiều indexed fields là **những mảng độc lập** trong cùng document. Ví dụ hai field array riêng có thể làm một compound index không hợp lệ tùy cấu trúc dữ liệu.

Điều này không phủ định trường hợp `"items.sku"` và `"items.qty"` cùng lấy từ **một array of documents**. Phải đọc mục **Compound Multikey Indexes** để biết cấu trúc nào được chấp nhận và cách index bounds được ghép.

Multikey index trên một array lớn cũng có chi phí: nhiều index entries, cập nhật thêm index entries khi array đổi, tăng kích thước index và working set. Không nhúng mảng không giới hạn chỉ vì MongoDB có multikey index.

### 13.3. Kiểm tra kế hoạch bằng `explain()`

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
}).explain("executionStats")
~~~

Quan sát các trường như:

| Trường / khái niệm | Cách đọc |
|---|---|
| `IXSCAN` | Có đoạn quét index trong execution plan. |
| `COLLSCAN` | Có đoạn quét collection. |
| `totalKeysExamined` | Số index entries được duyệt trong lần chạy quan sát. |
| `totalDocsExamined` | Số document phải xem xét. |
| `nReturned` | Số document kết quả. |
| Index bounds | Các khoảng giá trị index mà planner đã chọn, cần xem cùng cách xây compound index. |

Cấu trúc `explain` có thể thay đổi theo MongoDB version, execution engine và plan shape. Một truy vấn có `IXSCAN` chưa chắc tối ưu nếu quét quá nhiều keys hoặc fetch quá nhiều documents. Bộ mẫu bốn order quá nhỏ để kết luận index hiệu quả; cần đo trên dữ liệu tương đương production.

### 13.4. Unique multikey index không đồng nghĩa “SKU không trùng trong một order”

Giả sử muốn đảm bảo mỗi SKU chỉ xuất hiện **một lần trong cùng order**. Đừng tạo `unique index` trên `"items.sku"` rồi mặc định nó thực thi bất biến này:

- Unique multikey index kiểm tra tính duy nhất giữa **những documents khác nhau** theo index key; các phần tử lặp trong cùng document có ngữ nghĩa riêng.
- SKU có thể hợp lệ xuất hiện trong **nhiều orders**, nên unique index chỉ trên `items.sku` còn có thể cấm các order khác dùng cùng sản phẩm.
- Muốn mỗi order không trùng `sku` trong mảng, cần thiết kế identity/ràng buộc nghiệp vụ phù hợp, hoặc mô hình hóa line items thành documents riêng với compound unique index trên `orderId` và `sku` nếu đúng domain.

Không dùng index một cách máy móc để thay thế bất biến trên **các phần tử bên trong cùng một array**.

### 13.5. Sort, projection và giới hạn array

Sắp xếp document theo một indexed array field có những quy tắc đặc biệt (MongoDB có thể xét giá trị array theo thứ tự sort). Không nên nghĩ `sort({"items.qty": -1})` có nghĩa **sắp xếp các phần tử của `items` trong từng order**.

- `sort` ở cấp `find` sắp xếp **document order** trong tập kết quả.
- Muốn sort **các item bên trong một order**, cần aggregation `$sortArray` ở phiên bản hỗ trợ hoặc xử lý bằng pipeline phù hợp.
- Muốn lọc/sort/tách từng item thành dòng độc lập, `$unwind` là một lựa chọn rõ ràng.
- Nếu phải xử lý hàng triệu items độc lập, mô hình reference có thể phù hợp hơn là array lớn trong một document.

## 14. Truy vấn chính xác trong ứng dụng Java

Trong dự án Java, cùng một điều kiện MongoDB có thể được tạo qua builder của MongoDB Java Sync Driver. Ví dụ tương đương với:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
}
~~~

Trong Java (ý tưởng với Java Sync Driver):

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.elemMatch;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;

// Giả sử collection đã được lấy từ MongoDatabase:
MongoCollection<Document> orders = database.getCollection("orders");

var filter = elemMatch(
    "items",
    and(
        eq("sku", "BK-01"),
        gte("qty", 3)
    )
);

orders.find(filter).forEach(System.out::println);
~~~

Điểm cốt lõi là **`elemMatch("items", ...)`** thể hiện ranh giới **một item**. Nếu viết:

~~~java
var filterWithoutElemMatch = and(
    eq("items.sku", "BK-01"),
    gte("items.qty", 3)
);
~~~

thì nó mang ngữ nghĩa **có thể khớp các item khác nhau**, tương tự filter dot notation trong `mongosh`. Builder API không tự sửa ngữ nghĩa nghiệp vụ cho ứng dụng.

Với hai cấp array:

~~~java
var nestedFilter = elemMatch(
    "items",
    and(
        eq("sku", "BK-01"),
        elemMatch(
            "allocations",
            and(
                eq("warehouse", "HN"),
                gte("qty", 2)
            )
        )
    )
);
~~~

Một số ứng dụng dùng Spring Data MongoDB:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query(
    Criteria.where("items").elemMatch(
        Criteria.where("sku").is("BK-01")
            .and("qty").gte(3)
    )
);
~~~

Ở đây Spring Data sẽ xây một truy vấn theo ý nghĩa **cùng item**. Tuy nhiên, các API, overload và cách serialization có thể khác theo phiên bản Java Driver/Spring Data; luôn kiểm tra dependencies của dự án và tài liệu chính thức tương ứng.

## 15. Cách chuyển yêu cầu nghiệp vụ thành filter chính xác

Để tránh match sai vì nhiều cấp array, trước khi viết truy vấn hãy biến câu hỏi thành **một mệnh đề “tồn tại” hoặc “với mọi” rõ ràng**.

### 15.1. Một order chứa **bất kỳ item** nào có SKU BK-01

~~~text
Tồn tại i trong orders.items:
  items[i].sku = BK-01
~~~

Filter:

~~~javascript
{ "items.sku": "BK-01" }
~~~

### 15.2. Một order chứa item BK-01 với qty ít nhất 3

~~~text
Tồn tại i trong orders.items:
  items[i].sku = BK-01
  VÀ items[i].qty >= 3
~~~

Filter:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      qty: { $gte: 3 }
    }
  }
}
~~~

### 15.3. Một order có item BK-01 và có item PN-02

~~~text
Tồn tại i trong orders.items: items[i].sku = BK-01
VÀ tồn tại j trong orders.items: items[j].sku = PN-02
Không yêu cầu i = j.
~~~

Filter có thể dùng `$all` trên các SKU hoặc hai điều kiện `$elemMatch` bằng `$and`:

~~~javascript
{
  $and: [
    { items: { $elemMatch: { sku: "BK-01" } } },
    { items: { $elemMatch: { sku: "PN-02" } } }
  ]
}
~~~

Filter này khác với việc viết **một** `$elemMatch` chứa hai điều kiện equality mâu thuẫn trên cùng field `sku`. Một item có một giá trị `sku` đơn không thể vừa bằng BK-01 vừa bằng PN-02; yêu cầu chứa **hai item** phải được diễn đạt thành hai phép tồn tại hoặc tập điều kiện phù hợp.

### 15.4. Một item BK-01 có allocation HN với qty ít nhất 2

~~~text
Tồn tại i trong orders.items:
  items[i].sku = BK-01
  VÀ tồn tại j trong items[i].allocations:
      allocations[j].warehouse = HN
      VÀ allocations[j].qty >= 2
~~~

Filter:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "BK-01",
      allocations: {
        $elemMatch: {
          warehouse: "HN",
          qty: { $gte: 2 }
        }
      }
    }
  }
}
~~~

### 15.5. Không có item nào mang SKU BK-01

~~~text
KHÔNG TỒN TẠI i trong orders.items:
  items[i].sku = BK-01
~~~

Filter:

~~~javascript
{
  items: {
    $not: { $elemMatch: { sku: "BK-01" } }
  }
}
~~~

Yêu cầu này có thể đúng với document **không có `items`**. Nếu nghiệp vụ chỉ muốn các order có field `items` và field đó là array, kết hợp `$type: "array"`.

### 15.6. Tất cả items đều có qty ít nhất 1

“Mọi phần tử đều đạt điều kiện” tương đương “**không tồn tại** phần tử vi phạm”:

~~~javascript
{
  items: {
    $not: {
      $elemMatch: {
        qty: { $lt: 1 }
      }
    }
  }
}
~~~

Tuy nhiên, filter này **chưa chặn trường hợp item thiếu field `qty` hoặc `qty` sai kiểu**, cũng có thể khớp array rỗng theo logic “không có phần tử vi phạm”. Nếu yêu cầu là “mảng không rỗng, mỗi item có qty là số nguyên dương”, cần kết hợp kiểm tra tồn tại/kiểu và tốt nhất thiết lập **schema validation** phù hợp cho dữ liệu. Không cố dùng một query phủ định đơn giản làm validator toàn bộ schema khi dữ liệu có thể sai kiểu.

## 16. Những lỗi thường gặp

| Cách viết / suy luận dễ sai | Vấn đề | Cách đúng theo ý định |
|---|---|---|
| Hai điều kiện `"items.sku"` và `"items.qty"` riêng mà muốn **cùng item** | Có thể khớp **hai item khác nhau**. | Dùng `items: {$elemMatch:{sku:..., qty:...}}`. |
| Một `$elemMatch` ở cấp item nhưng bên trong có nhiều điều kiện trên `allocations` | Có thể khớp **hai allocations khác nhau**. | Dùng `$elemMatch` lồng trong `allocations`. |
| Filter item SKU rồi tưởng result chỉ chứa item đó | `find` chọn **document cha**, array vẫn đầy đủ. | Projection `$elemMatch` cho phần tử đầu hoặc aggregation `$filter` cho tất cả. |
| Dùng projection `$elemMatch` và kỳ vọng trả mọi phần tử | Projection chỉ giữ **phần tử khớp đầu tiên**. | Dùng `$filter`. |
| Dùng `"items.0.sku"` để tìm SKU trong bất kỳ item | Chỉ kiểm tra **vị trí 0**. | Dùng `"items.sku"` hoặc `$elemMatch`. |
| Dùng `$ne` trên `items.sku` để tìm ít nhất một SKU khác | `$ne` thường diễn đạt **không có giá trị bị loại** trên đường dẫn, kể cả field thiếu. | Dùng `$elemMatch` với `$ne` và `$exists` nếu cần. |
| Dùng equality với `null` để phát hiện field thiếu | `null` có thể khớp field thiếu **hoặc** null. | Dùng `$exists`/`$type` phù hợp. |
| Dùng `$size` với `$gte` | `$size` yêu cầu kích thước cụ thể. | Dùng chỉ số tồn tại hoặc trường count do ứng dụng duy trì đúng quy tắc. |
| So sánh nguyên embedded document để kiểm tra một field | Equality nguyên document phụ thuộc toàn cấu trúc và **thứ tự field**. | Dùng dot notation cho field cần tìm. |
| Dùng `items.$` để cập nhật mọi item cùng SKU | `$` chỉ sửa phần tử khớp đầu tiên. | Dùng `$[line]` + `arrayFilters`. |
| Dùng `items.$[]` nhưng chỉ muốn sửa một item | `$[]` áp dụng lên mọi phần tử. | Dùng `$[line]` hoặc positional `$` đúng điều kiện. |
| Có multikey index nên mọi query array nhanh | Hiệu năng còn phụ thuộc selectivity, index bounds và document fetch. | Đo `explain("executionStats")` trên dữ liệu đại diện. |
| Unique index trên `items.sku` sẽ đảm bảo mỗi order không trùng SKU | Unique multikey có ngữ nghĩa **giữa documents** và có thể cấm SKU xuất hiện trong các order khác. | Thiết kế ràng buộc trong aggregate hoặc mô hình hóa line items riêng. |
| Giữ mọi phần tử con trong một mảng mãi mãi | Có thể thành **unbounded array**, document lớn/hot và chạm 16 MiB. | Tách thành collection riêng hoặc dùng subset/bucket có giới hạn. |

### 16.1. Thực hành đọc logic trước khi chạy query

Trước khi đưa một filter vào code review, hãy trả lời ba câu:

1. **Điều kiện áp lên document cha hay một phần tử của mảng?** Ví dụ `status` thuộc order, `qty` thuộc item.
2. **Nếu có nhiều điều kiện, chúng phải thỏa trên cùng một phần tử không?** Nếu có, chọn `$elemMatch` tại đúng ranh giới array.
3. **Kết quả cần toàn document, một phần tử, hay tất cả phần tử khớp?** Phân biệt query filter, projection và aggregation.

Việc nêu rõ ý nghĩa của một câu query bằng lời giúp review logic dễ hơn so với chỉ nhìn dãy toán tử MongoDB.

### 16.2. Ranh giới giữa lựa chọn schema và lựa chọn truy vấn

Array of embedded documents thường hợp lý khi số phần tử **có giới hạn** và thường được đọc/cập nhật cùng document cha. Với mảng tăng không giới hạn như hàng triệu comments hoặc event logs, việc truy vấn bằng `$elemMatch` đúng cú pháp cũng không giải quyết vấn đề mô hình dữ liệu.

Nếu cần thường xuyên filter/sort/paginate từng phần tử một cách độc lập trên tập dữ liệu rất lớn, có thể cân nhắc tách phần tử thành **document riêng** với khóa tham chiếu `orderId`/`parentId`. Khi đó query trên item là query collection độc lập, index/sort/pagination rõ ràng hơn. Đây là quyết định dựa trên **access pattern và cardinality**, không phải giới hạn riêng của `$elemMatch`.

## 17. Bài tập thực hành

Sử dụng bộ dữ liệu `array_query_lab.orders` ở mục 2. Trước những bài cập nhật, có thể chạy lại vòng lặp `replaceOne` ở mục 2 để phục hồi dữ liệu demo về trạng thái ban đầu.

### Bài 1 — Tìm order có BK-01

Viết filter lấy order có **ít nhất một item** với `sku = "BK-01"`. Dự đoán `_id` được trả về.

**Đáp án:**

~~~javascript
lab.orders.find(
  { "items.sku": "BK-01" },
  { _id: 1 }
)
// O-100, O-200, O-300.
~~~

### Bài 2 — Hai predicate có khớp cùng item không?

So sánh hai câu:

~~~javascript
// A:
lab.orders.find({
  "items.sku": "BK-01",
  "items.qty": { $gte: 3 }
})

// B:
lab.orders.find({
  items: {
    $elemMatch: { sku: "BK-01", qty: { $gte: 3 } }
  }
})
~~~

**Đáp án:** A chọn **O-100, O-200, O-300** vì mỗi predicate có thể khớp phần tử khác nhau. B chỉ chọn **O-200** vì cùng item BK-01 có qty 3.

### Bài 3 — Hỏi đúng mảng lồng

Tìm order có item BK-01 và **trong item đó** có allocation `warehouse = "HN"` với `qty >= 2`.

**Đáp án:**

~~~javascript
lab.orders.find({
  items: {
    $elemMatch: {
      sku: "BK-01",
      allocations: {
        $elemMatch: {
          warehouse: "HN",
          qty: { $gte: 2 }
        }
      }
    }
  }
})
// O-200.
~~~

### Bài 4 — Truy vấn theo vị trí

Tìm order có phần tử thứ hai (`index 1`) với qty ít nhất 3.

**Đáp án:**

~~~javascript
lab.orders.find(
  { "items.1.qty": { $gte: 3 } },
  { _id: 1 }
)
// O-100 và O-300.
~~~

### Bài 5 — Tìm order không có item nào

Chỉ chọn document mà field `items` **là array rỗng**, không lấy document thiếu `items` hoặc có `items: null`.

**Đáp án:**

~~~javascript
lab.orders.find(
  { items: { $size: 0 } },
  { _id: 1 }
)
// O-400.
~~~

### Bài 6 — Có cả hai SKU khác nhau

Tìm order chứa **BK-01 và PN-02**, không yêu cầu chúng nằm cùng phần tử.

**Đáp án gợi ý:**

~~~javascript
lab.orders.find({
  "items.sku": { $all: ["BK-01", "PN-02"] }
})
// O-100, O-200, O-300.
~~~

### Bài 7 — Projection một item

Chỉ chọn order O-100, trả `status` và **item đầu tiên** có SKU BK-03, thay vì toàn bộ items.

**Đáp án:**

~~~javascript
lab.orders.find(
  { _id: "O-100" },
  {
    status: 1,
    items: { $elemMatch: { sku: "BK-03" } }
  }
)
~~~

### Bài 8 — Lọc nhiều items bằng aggregation

Với O-100, trả một field mới `bookItems` chỉ chứa items có SKU trong `["BK-01", "BK-03"]`.

**Đáp án:**

~~~javascript
lab.orders.aggregate([
  { $match: { _id: "O-100" } },
  {
    $project: {
      bookItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $in: ["$$item.sku", ["BK-01", "BK-03"]]
          }
        }
      }
    }
  }
])
~~~

`bookItems` chứa hai item BK-01 và BK-03. Đây là kết quả tạm thời của aggregation, **không sửa document lưu trữ**.

### Bài 9 — Cập nhật một item bằng `arrayFilters`

Với O-100, đánh dấu `picked: true` trên mọi item có SKU BK-01.

**Đáp án:**

~~~javascript
lab.orders.updateOne(
  { _id: "O-100" },
  { $set: { "items.$[line].picked": true } },
  { arrayFilters: [{ "line.sku": "BK-01" }] }
)
~~~

### Bài 10 — Cập nhật allocation ở hai cấp array

Với O-200, tăng `qty` của allocation kho HN nằm trong item BK-01 thêm một đơn vị.

**Đáp án:**

~~~javascript
lab.orders.updateOne(
  { _id: "O-200" },
  {
    $inc: {
      "items.$[line].allocations.$[alloc].qty": 1
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BK-01" },
      { "alloc.warehouse": "HN" }
    ]
  }
)
~~~

### Bài 11 — Phủ định có phải tồn tại phần tử khác không?

Giả sử order chứa `items: [{sku:"BK-01"},{sku:"PN-02"}]`. Filter `{"items.sku":{$ne:"BK-01"}}` có chọn order này chỉ vì PN-02 khác BK-01 không?

**Đáp án:** **Không.** Filter diễn tả không có giá trị BK-01 phù hợp trên đường dẫn. Muốn “tồn tại item khác BK-01”, dùng `items: {$elemMatch:{sku:{$ne:"BK-01"}}}`, và thêm `$exists` nếu không muốn match item thiếu SKU.

### Bài 12 — Chọn mô hình dữ liệu

Một bài viết có thể có hàng triệu comments, mỗi comment cần tìm theo author, sort theo timestamp và phân trang. Có nên nhúng tất cả vào một array của article để dùng `$elemMatch`?

**Đáp án gợi ý:** Không nên có **unbounded array** trong document cha. Thường phù hợp để comments thành collection riêng với `articleId`, `authorId`, `createdAt` và index theo access pattern. Có thể nhúng **subset nhỏ có giới hạn** để hiển thị nhanh nếu cần.

## 18. Tài liệu MongoDB chính thức

Khi tra cứu, luôn chọn **MongoDB Database Manual theo phiên bản server đang dùng**, vì cú pháp một số phương thức, index/aggregation stages và giới hạn execution có thể thay đổi. Các link `/docs/manual/` thường dẫn tới tài liệu hiện hành; ví dụ cố định phiên bản 8.0 là đường dẫn `/docs/v8.0/`.

- [Query an Array of Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/) — dot notation và `$elemMatch` trên mảng document.
- [Query Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-embedded-documents/) — đường dẫn nested object và equality trên embedded document.
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/) — equality, `$all`, điều kiện trên array và phần tử.
- [`$elemMatch` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — quy tắc cùng phần tử trong filter.
- [`$all` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/all/) — nhiều giá trị/điều kiện trên array.
- [`$size` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/size/) — điều kiện kích thước array.
- [`$exists` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — field có tồn tại hay không.
- [`$ne` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/ne/) — ngữ nghĩa không bằng với array và field thiếu.
- [`$elemMatch` Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/elemMatch/) — trả phần tử khớp đầu tiên.
- [Positional `$` Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/positional/) — chọn phần tử mảng đầu tiên theo điều kiện query.
- [`$slice` Projection Operator](https://www.mongodb.com/docs/manual/reference/operator/projection/slice/) — lấy một đoạn array.
- [Aggregation `$filter`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — lọc các phần tử trong array để tạo output.
- [Aggregation `$unwind`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/) — đưa mỗi phần tử array thành pipeline document.
- [Filtered Positional Update `$[identifier]`](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/) — `arrayFilters` khi cập nhật phần tử.
- [Positional Update `$`](https://www.mongodb.com/docs/manual/reference/operator/update/positional/) và [All Positional Update `$[]`](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/) — cập nhật phần tử đầu tiên hoặc tất cả phần tử.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — indexing arrays, compound bounds, các giới hạn index.
- [MongoDB 8.0 — Query an Array of Documents](https://www.mongodb.com/docs/v8.0/tutorial/query-array-of-documents/) — ví dụ trang tài liệu có đường dẫn cố định theo phiên bản.
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/) — builders như `Filters.elemMatch`; chọn đúng phiên bản driver của dự án.

Khi viết query trên mảng document, câu hỏi quyết định là: **những điều kiện này có cần thỏa trên cùng một phần tử không?** Nếu có, đặt `$elemMatch` đúng ranh giới array; nếu đường dẫn đi qua nhiều array, có thể cần `$elemMatch` lồng nhau. Sau đó mới quyết định **lấy cả document, một phần tử hay tất cả phần tử khớp**, và chọn filter/projection/aggregation tương ứng. Cách diễn đạt rõ ràng đó giúp tránh những kết quả khớp nhầm khó phát hiện ở dữ liệu thật.
