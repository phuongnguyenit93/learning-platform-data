# Truy vấn trường lồng nhau bằng dot notation và so sánh nguyên document trong MongoDB

MongoDB lưu dữ liệu theo **document BSON**, trong đó một field có thể chứa giá trị đơn giản như chuỗi, số, boolean hoặc chứa **document nhúng** (embedded document) và **mảng**. Ví dụ, một khách hàng có thể có `profile.address.city` nằm sâu trong đối tượng `profile`; đơn hàng nằm trong mảng `orders`, mỗi phần tử lại có các field riêng.

Khi truy vấn document lồng nhau, có hai cách dễ bị nhầm lẫn:

1. **Dot notation**: truy cập field ở sâu trong document bằng đường dẫn, chẳng hạn `"profile.address.city": "Hà Nội"`.
2. **So sánh nguyên embedded document**: so sánh giá trị object hoàn chỉnh, chẳng hạn `"profile.address": { city: "Hà Nội", district: "Ba Đình", zip: "100000" }`.

Hai cách viết này có thể cho **kết quả khác nhau**. Dot notation thường chỉ kiểm tra field được chỉ định, trong khi equality với nguyên embedded document yêu cầu cả cấu trúc giá trị và **thứ tự các field** khớp chính xác. Bài học giải thích cách đọc, viết và lựa chọn hai kiểu truy vấn trong ngữ cảnh phần **Truy vấn document** của MongoDB.

## 1. Hiểu cấu trúc document và đường dẫn field

Một document ví dụ:

```javascript
{
  _id: "c101",
  name: "An",
  verified: true,
  profile: {
    address: {
      city: "Hà Nội",
      district: "Ba Đình",
      zip: "100000"
    },
    contact: {
      email: "an@example.test"
    }
  },
  orders: [
    { code: "A", status: "pending", total: 100 },
    { code: "B", status: "paid", total: 300 }
  ]
}
```

Cấu trúc phân cấp của document:

```text
Khách hàng (_id = "c101")
├── name: "An"
├── verified: true
├── profile                             object
│   ├── address                         object
│   │   ├── city: "Hà Nội"
│   │   ├── district: "Ba Đình"
│   │   └── zip: "100000"
│   └── contact                         object
│       └── email: "an@example.test"
└── orders                              array
    ├── [0] {code: "A", status: "pending", total: 100}
    └── [1] {code: "B", status: "paid", total: 300}
```

Ở đây:

| Thành phần | Kiểu giá trị | Cách truy cập bằng dot notation |
| --- | --- | --- |
| `name` | String ở cấp gốc | `"name"` |
| `profile` | Embedded document | `"profile"` |
| `profile.address` | Embedded document trong `profile` | `"profile.address"` |
| `profile.address.city` | String nằm trong hai lớp object | `"profile.address.city"` |
| `profile.contact.email` | String nằm trong object khác | `"profile.contact.email"` |
| `orders` | Array của các object | `"orders"` |
| `orders.code` | Các giá trị `code` bên trong phần tử của mảng | `"orders.code"` |
| `orders.0.code` | `code` của phần tử ở vị trí 0 | `"orders.0.code"` |

**Dot notation** là cách viết tên đường dẫn gồm các cấp được phân cách bởi dấu chấm. Với bộ lọc truy vấn có field lồng nhau, hãy đặt đường dẫn trong dấu nháy:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
})
```

Nếu viết `profile.address.city` như một biểu thức JavaScript trần ở vị trí khóa của object, `mongosh` sẽ không hiểu đó là một tên field hợp lệ theo ý định. Dùng chuỗi `"profile.address.city"` để biểu diễn chính xác đường dẫn.

## 2. Tạo bộ dữ liệu thực hành có các trường hợp khác nhau

Kết nối MongoDB từ `mongosh`, chọn database riêng cho bài học:

```javascript
use document_query_lab
```

Chạy đoạn sau **một lần** trên collection `customers` mới hoặc trống:

```javascript
db.customers.insertMany([
  {
    _id: "c101",
    name: "An",
    verified: true,
    profile: {
      address: {
        city: "Hà Nội",
        district: "Ba Đình",
        zip: "100000"
      },
      contact: { email: "an@example.test" }
    },
    orders: [
      {
        code: "A",
        status: "pending",
        total: 100,
        items: [
          { sku: "P-1", qty: 1 },
          { sku: "P-2", qty: 2 }
        ]
      },
      {
        code: "B",
        status: "paid",
        total: 300,
        items: [{ sku: "P-3", qty: 1 }]
      }
    ]
  },
  {
    _id: "c102",
    name: "Bình",
    verified: false,
    profile: {
      address: {
        city: "Hà Nội",
        district: "Ba Đình",
        zip: "100000",
        note: "Cổng số 2"
      }
    },
    orders: [
      { code: "A", status: "shipped", total: 150 },
      { code: "B", status: "paid", total: 250 }
    ]
  },
  {
    _id: "c103",
    name: "Chi",
    verified: true,
    profile: {
      address: {
        district: "Ba Đình",
        city: "Hà Nội",
        zip: "100000"
      }
    },
    orders: [
      { code: "A", status: "paid", total: 180 }
    ]
  },
  {
    _id: "c104",
    name: "Dũng",
    verified: true,
    profile: {
      address: {
        city: "Đà Nẵng",
        district: "Hải Châu",
        zip: "550000"
      }
    },
    orders: [
      { code: "C", status: "pending", total: 90 }
    ]
  },
  {
    _id: "c105",
    name: "Em",
    verified: false,
    profile: { address: null },
    orders: []
  },
  {
    _id: "c106",
    name: "Giang",
    verified: false,
    profile: {},
    orders: []
  }
])
```

Ta cố ý tạo ra ba trường hợp đặc biệt:

- `c101`: `address` có đúng ba field theo thứ tự `city`, `district`, `zip`.
- `c102`: `address` có ba field tương tự nhưng **thêm** `note`.
- `c103`: `address` có cùng tên field và giá trị như `c101`, nhưng **đảo thứ tự** `district` lên trước `city`.

Ngoài ra, `c105` lưu `address: null` còn `c106` **không có field** `address`. Điều này giúp phân biệt truy vấn đường dẫn, equality với object, null và field bị thiếu.

Nếu chạy lại `insertMany()` với các `_id` tương tự, MongoDB sẽ báo lỗi duplicate key cho document đã tồn tại. Không cần xóa dữ liệu thật chỉ để chạy lại ví dụ; hãy dùng database hoặc collection thực hành riêng.

## 3. Truy vấn một field lồng nhau bằng dot notation

### 3.1. So sánh giá trị của field sâu

Tìm khách hàng có địa chỉ ở Hà Nội:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
})
```

Với dữ liệu ban đầu, kết quả khớp các document có `_id` là **`c101`, `c102`, `c103`**. Truy vấn chỉ kiểm tra giá trị `city`, nên **không quan tâm** object `address` còn các field khác, cũng không quan tâm `city` đứng trước hay sau `district`.

Truy vấn theo email:

```javascript
db.customers.find({
  "profile.contact.email": "an@example.test"
})
```

Truy vấn này khớp `c101` vì `profile` chứa object `contact` có field `email` tương ứng.

### 3.2. So sánh theo nhiều field con

Tìm khách hàng ở Hà Nội, quận Ba Đình:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội",
  "profile.address.district": "Ba Đình"
})
```

Kết quả vẫn là **`c101`, `c102`, `c103`**. Hai cặp khóa–giá trị trong filter được kết hợp như điều kiện **AND**: `city` và `district` đều phải khớp. Chúng không yêu cầu object `address` chỉ có đúng hai field.

Có thể viết tường minh bằng `$and`:

```javascript
db.customers.find({
  $and: [
    { "profile.address.city": "Hà Nội" },
    { "profile.address.district": "Ba Đình" }
  ]
})
```

Hai kiểu filter trên tương đương trong ví dụ này. `$and` hữu ích nếu cần tổ chức điều kiện phức tạp hoặc tránh việc lặp cùng một khóa trong object JavaScript.

### 3.3. Toán tử so sánh với field lồng nhau

Dot notation kết hợp được với các toán tử truy vấn thông thường:

```javascript
// So sánh chuỗi trong field lồng nhau
db.customers.find({
  "profile.address.zip": { $in: ["100000", "550000"] }
})

// Kiểm tra giá trị không nằm trong một tập nhất định
db.customers.find({
  "profile.address.city": { $nin: ["Đà Nẵng", "Huế"] }
})
```

`$nin` còn khớp các document **thiếu** field được truy vấn, nên không nên diễn giải điều kiện thứ hai đơn thuần là “đã biết thành phố và thành phố đó không phải Đà Nẵng hoặc Huế”. Nếu cần field phải tồn tại, bổ sung `$exists: true` và điều kiện kiểu phù hợp:

```javascript
db.customers.find({
  "profile.address.city": {
    $exists: true,
    $nin: ["Đà Nẵng", "Huế"]
  }
})
```

Khi field là số, dùng `$gt`, `$gte`, `$lt`, `$lte` với giá trị số thích hợp. Đừng nhầm mã bưu chính dạng `"100000"` với một số dùng để tính toán; việc so sánh chuỗi và số có quy tắc kiểu khác nhau.

## 4. So sánh nguyên embedded document bằng equality

Ngoài truy vấn field con, MongoDB cho phép so sánh **giá trị object hoàn chỉnh** của một field:

```javascript
db.customers.find({
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
})
```

Với tập dữ liệu trên, truy vấn này chỉ khớp **`c101`**.

Lý do là phép so sánh equality với embedded document đòi hỏi:

1. **Đủ và đúng các field** được so sánh.
2. **Không có field thừa** trong embedded document tại vị trí được so sánh.
3. **Giá trị và kiểu dữ liệu** của các field khớp.
4. **Thứ tự các field** trong embedded document khớp thứ tự được cung cấp trong giá trị truy vấn.

So sánh ba document quan trọng:

| Document | `profile.address` | Kết quả khi so sánh nguyên document ở trên |
| --- | --- | --- |
| `c101` | `{city:"Hà Nội", district:"Ba Đình", zip:"100000"}` | Khớp |
| `c102` | Như `c101` nhưng thêm `note:"Cổng số 2"` | Không khớp vì thừa field |
| `c103` | `{district:"Ba Đình", city:"Hà Nội", zip:"100000"}` | Không khớp vì thứ tự field khác |

Điều quan trọng là **trong MongoDB, field order của embedded document có ý nghĩa đối với equality match**, dù trong nhiều ngữ cảnh lập trình viên thường xem object giống tập các cặp khóa–giá trị không thứ tự.

### 4.1. Đổi thứ tự trong giá trị truy vấn có thể đổi kết quả

```javascript
db.customers.find({
  "profile.address": {
    district: "Ba Đình",
    city: "Hà Nội",
    zip: "100000"
  }
})
```

Giá trị truy vấn này giữ nguyên ba cặp field/giá trị nhưng đặt `district` đầu tiên; với dữ liệu mẫu, nó khớp **`c103`**, không khớp `c101`.

So sánh nguyên document hữu ích khi **toàn bộ object là một giá trị phải trùng khít**, chẳng hạn một cấu hình hoặc một mẫu dữ liệu có thứ tự và cấu trúc ổn định. Khi cần tra cứu dựa trên vài thuộc tính bất kể field còn lại, dot notation thường diễn đạt đúng ý định hơn.

### 4.2. `$eq` với object cũng là equality

Hai cách sau cùng hướng tới so sánh nguyên object:

```javascript
db.customers.find({
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
})

db.customers.find({
  "profile.address": {
    $eq: {
      city: "Hà Nội",
      district: "Ba Đình",
      zip: "100000"
    }
  }
})
```

`$eq` làm rõ đây là phép so sánh giá trị. Nó không chuyển equality với embedded document thành cách so sánh bất chấp thứ tự các field.

### 4.3. Equality với một object bên trong field khác

Giả sử muốn so sánh toàn bộ `profile`, cần cung cấp đủ các field thuộc `profile`, bao gồm cả `address` và `contact` nếu chúng thực sự tồn tại:

```javascript
db.customers.find({
  profile: {
    address: {
      city: "Hà Nội",
      district: "Ba Đình",
      zip: "100000"
    },
    contact: { email: "an@example.test" }
  }
})
```

Truy vấn này khớp `c101` trong dữ liệu mẫu. Nếu object `profile` có thêm field như `preferences`, equality nguyên `profile` sẽ không còn khớp cho dù các thông tin địa chỉ và liên hệ không đổi.

## 5. Dot notation và equality nguyên document: đối chiếu trực tiếp

Giả sử mục tiêu là “tìm mọi khách hàng có thành phố Hà Nội và quận Ba Đình, bất kể có lưu thêm ghi chú giao hàng hay không”.

**Viết đúng ý định bằng dot notation:**

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội",
  "profile.address.district": "Ba Đình"
})
```

Kết quả: `c101`, `c102`, `c103`.

**Viết bằng equality nguyên address:**

```javascript
db.customers.find({
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
})
```

Kết quả: `c101`.

| Tiêu chí | Dot notation theo từng field | Equality nguyên embedded document |
| --- | --- | --- |
| Đối tượng so sánh | Giá trị của một hoặc nhiều đường dẫn con | Toàn bộ object tại một field |
| Field khác không được nêu | Không cản trở match | Có thể làm mất match nếu xuất hiện trong object |
| Thứ tự field của object | Không quan trọng với điều kiện field con | Quan trọng |
| Thêm field mới vào object | Truy vấn cũ thường vẫn khớp | Có thể không còn khớp |
| Phù hợp khi | Lọc theo một tập thuộc tính | Cần cấu trúc object khớp chính xác |
| Ví dụ | `"profile.address.city": "Hà Nội"` | `"profile.address": {city:"Hà Nội",district:"Ba Đình",zip:"100000"}` |

Không có cách nào “tốt tuyệt đối” trong mọi trường hợp. Chọn loại so sánh phải dựa trên **yêu cầu nghiệp vụ**. Khi nghiệp vụ mô tả những thuộc tính cụ thể, truy vấn đường dẫn thường ổn định hơn trước sự phát triển của schema.

## 6. `null`, field vắng mặt và object rỗng

Trong dữ liệu mẫu:

```javascript
// c105
{ _id: "c105", profile: { address: null } }

// c106
{ _id: "c106", profile: {} }
```

Hai document này khác nhau về mặt dữ liệu:

- `c105` có field `profile.address`, nhưng giá trị là BSON `null`.
- `c106` không có field `profile.address`.

Truy vấn equality với `null`:

```javascript
db.customers.find({
  "profile.address": null
})
```

Trong MongoDB, bộ lọc equality dạng này khớp cả trường có giá trị `null` **và** trường không tồn tại; vì vậy nó trả về cả `c105` và `c106` trong tập mẫu.

Muốn kiểm tra field có tồn tại:

```javascript
db.customers.find({
  "profile.address": { $exists: true }
})
```

Điều kiện `$exists: true` vẫn khớp `c105`, vì `address` tồn tại dù giá trị là `null`. Trái lại:

```javascript
db.customers.find({
  "profile.address": { $exists: false }
})
```

trả về `c106` (nếu không có document nào khác thiếu đường dẫn đó).

Muốn chỉ tìm giá trị BSON `null` thực sự:

```javascript
db.customers.find({
  "profile.address": { $type: "null" }
})
```

Để chỉ chọn `address` có kiểu object:

```javascript
db.customers.find({
  "profile.address": { $type: "object" }
})
```

Ví dụ này khớp `c101`, `c102`, `c103`, `c104`. Nếu cần lấy những document có `city` đúng kiểu chuỗi, có thể kiểm tra đường dẫn cụ thể:

```javascript
db.customers.find({
  "profile.address.city": { $type: "string" }
})
```

Một truy vấn lồng sâu như `"profile.address.city": null` cũng cần được hiểu thận trọng: nó có thể khớp khi đường dẫn `city` không tồn tại. Hãy kết hợp `$exists` hoặc `$type` khi cần phân biệt rõ “không có địa chỉ”, “địa chỉ rỗng” và “thành phố có giá trị null”.

## 7. Dot notation khi đi qua mảng các object

Document `c101` có `orders` là mảng:

```javascript
{
  orders: [
    {
      code: "A",
      status: "pending",
      total: 100,
      items: [
        { sku: "P-1", qty: 1 },
        { sku: "P-2", qty: 2 }
      ]
    },
    {
      code: "B",
      status: "paid",
      total: 300,
      items: [{ sku: "P-3", qty: 1 }]
    }
  ]
}
```

MongoDB có thể dùng dot notation để truy vấn field nằm trong các phần tử mảng:

```javascript
db.customers.find({
  "orders.code": "A"
})
```

Điều kiện trên khớp document nếu **ít nhất một phần tử** trong mảng `orders` có `code: "A"`. Với dữ liệu mẫu, kết quả gồm `c101`, `c102`, `c103`.

Truy vấn field của phần tử ở vị trí đầu tiên:

```javascript
db.customers.find({
  "orders.0.code": "A"
})
```

`0` chỉ phần tử đầu tiên trong mảng. Đây là điều kiện **theo vị trí**, nên không phù hợp nếu thứ tự phần tử thay đổi mà nghiệp vụ chỉ quan tâm `code`. Trong hệ thống thực tế, thường ưu tiên tìm phần tử theo mã/ngữ nghĩa thay vì hard-code vị trí.

Truy vấn qua hai cấp mảng/object:

```javascript
db.customers.find({
  "orders.items.sku": "P-2"
})
```

Driver/server đi qua các phần tử của `orders`, rồi các phần tử `items` bên trong để tìm `sku` phù hợp. Trong dữ liệu mẫu, `c101` chứa mặt hàng `P-2`.

## 8. Nhiều điều kiện trên mảng: khi nào cần `$elemMatch`?

Đây là trường hợp quan trọng khi so sánh dot notation với cấu trúc object lồng nhau.

Giả sử nghiệp vụ yêu cầu: “Tìm khách hàng có một đơn hàng mã `A` **đã thanh toán**”.

Nếu viết:

```javascript
db.customers.find({
  "orders.code": "A",
  "orders.status": "paid"
})
```

MongoDB có thể thỏa `"orders.code": "A"` bằng **một phần tử** và thỏa `"orders.status": "paid"` bằng **phần tử khác**. Với tập dữ liệu mẫu:

- `c101`: đơn `A` đang `pending`, còn đơn `B` là `paid` → **vẫn khớp** truy vấn ở trên.
- `c102`: đơn `A` là `shipped`, còn đơn `B` là `paid` → **vẫn khớp**.
- `c103`: đơn `A` là `paid` → khớp.

Kết quả của bộ lọc dot notation tách rời: `c101`, `c102`, `c103`. Nhưng chỉ **`c103`** thỏa yêu cầu “cùng một đơn hàng mã A đã thanh toán”.

Sử dụng `$elemMatch` để buộc các điều kiện nằm trên **cùng phần tử object**:

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      status: "paid"
    }
  }
})
```

Lần này kết quả chỉ có `c103`.

### 8.1. Một điều kiện và nhiều điều kiện trên array khác nhau

| Nhu cầu | Bộ lọc nên dùng |
| --- | --- |
| Có bất kỳ order nào mang mã A | `{ "orders.code": "A" }` |
| Có bất kỳ order nào mang trạng thái paid | `{ "orders.status": "paid" }` |
| Có order mã A và có order paid, có thể là hai order khác nhau | `{ "orders.code": "A", "orders.status": "paid" }` |
| Có **cùng một order** mã A và trạng thái paid | `{ orders: { $elemMatch: { code: "A", status: "paid" } } }` |

Dot notation **không sai** ở đây; nó đang biểu diễn một điều kiện khác. Sai sót xảy ra khi dùng nó để suy ra các điều kiện phải đồng thời đúng trên cùng phần tử mảng.

### 8.2. `$elemMatch` lồng nhau cho mảng trong mảng

Giả sử cần tìm khách hàng có **một order mã `A`**, trong order đó có **một item mã `P-2` và số lượng từ 2 trở lên**:

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      items: {
        $elemMatch: {
          sku: "P-2",
          qty: { $gte: 2 }
        }
      }
    }
  }
})
```

Hai lớp `$elemMatch` có ý nghĩa:

1. Lớp ngoài: `code` và điều kiện `items` phải cùng thuộc **một order**.
2. Lớp trong: `sku` và `qty` phải cùng thuộc **một item** của order đó.

Trong dữ liệu mẫu, truy vấn khớp `c101`. Nếu chỉ viết `"orders.code": "A"`, `"orders.items.sku": "P-2"` và `"orders.items.qty": { $gte: 2 }`, mỗi điều kiện có thể được thỏa bởi các phần tử khác nhau; khi đó kết quả có thể không đáp ứng yêu cầu của nghiệp vụ.

## 9. Phân biệt equality với object trong array và equality nguyên array

Giả sử document:

```javascript
{
  favoriteColors: ["red", "blue"],
  address: {
    city: "Hà Nội",
    zip: "100000"
  }
}
```

Kiểm tra có phần tử `"blue"` trong mảng:

```javascript
db.preferences.find({
  favoriteColors: "blue"
})
```

Đây là dạng equality với **giá trị phần tử của array**, nên chỉ cần array có `"blue"`.

Kiểm tra **toàn bộ array** có đúng hai phần tử theo đúng thứ tự:

```javascript
db.preferences.find({
  favoriteColors: ["red", "blue"]
})
```

Truy vấn này khớp array chính xác `["red", "blue"]`, khác với `["blue", "red"]` hoặc `["red", "blue", "green"]`.

Kiểm tra **toàn bộ embedded document `address`**:

```javascript
db.preferences.find({
  address: {
    city: "Hà Nội",
    zip: "100000"
  }
})
```

Đây là equality nguyên object, yêu cầu field và thứ tự đúng. Cả hai đều là phép so sánh giá trị tổng thể, nhưng array có quy tắc thứ tự phần tử, còn embedded document có quy tắc thứ tự field.

Trong ví dụ trên, collection `preferences` chỉ là tên minh họa. Nếu muốn thử thực tế, cần tạo document trong collection đó trước.

## 10. Projection: chỉ trả về những field lồng nhau cần thiết

Filter quyết định document nào khớp; **projection** quyết định field nào được trả về.

```javascript
db.customers.find(
  { "profile.address.city": "Hà Nội" },
  {
    _id: 0,
    name: 1,
    "profile.address.city": 1,
    "profile.address.zip": 1
  }
)
```

Với dữ liệu mẫu, truy vấn trả về tên cùng các field được chọn cho `c101`, `c102`, `c103`. Cấu trúc kết quả vẫn là **object lồng nhau**:

```javascript
{
  name: "An",
  profile: {
    address: {
      city: "Hà Nội",
      zip: "100000"
    }
  }
}
```

Dot notation trong projection không biến đường dẫn thành một field cấp gốc mang tên chữ `"profile.address.city"`. MongoDB dựng lại phần cấu trúc cần thiết của document.

Với mảng các object, chọn một field con trong projection có thể trả về field đó ở nhiều phần tử mảng. Nếu chỉ muốn **một phần tử mảng đầu tiên thỏa điều kiện**, hãy nghiên cứu projection `$elemMatch` theo đúng nhu cầu; nếu cần biến đổi cấu trúc hay lọc sâu nhiều phần tử, aggregation pipeline với `$project` và `$filter` thường diễn đạt rõ hơn.

## 11. Dot notation trong cập nhật: cùng cách viết, khác mục đích

Mặc dù bài học tập trung vào truy vấn, dot notation còn xuất hiện khi **cập nhật field lồng nhau**. Điều này dễ gây nhầm với việc thay nguyên object.

Chỉ sửa `city` trong `profile.address`:

```javascript
db.customers.updateOne(
  { _id: "c101" },
  { $set: { "profile.address.city": "Hải Phòng" } }
)
```

Cách cập nhật này giữ lại `district` và `zip`.

Ngược lại:

```javascript
db.customers.updateOne(
  { _id: "c101" },
  {
    $set: {
      "profile.address": { city: "Hải Phòng" }
    }
  }
)
```

Lệnh này **thay toàn bộ** giá trị `profile.address` thành object chỉ có `city`. Các field `district`, `zip` trước đó không được giữ lại. Trong bài thực hành, những lệnh update này **làm thay đổi dữ liệu mẫu**, vì vậy nếu muốn kiểm tra tiếp các đáp án ở mục dưới hãy chạy truy vấn trên dữ liệu ban đầu hoặc tạo lại bộ dữ liệu riêng.

Tương tự, để cập nhật một order theo điều kiện, có thể dùng positional operator hoặc `arrayFilters` thay vì suy đoán vị trí index cố định:

```javascript
db.customers.updateOne(
  { _id: "c101" },
  { $set: { "orders.$[order].status": "paid" } },
  {
    arrayFilters: [
      { "order.code": "A" }
    ]
  }
)
```

`$[order]` áp dụng thay đổi cho các phần tử `orders` thỏa bộ lọc, tránh phụ thuộc vào việc đơn `A` nằm ở vị trí 0 hay một vị trí khác.

## 12. Index cho các truy vấn field lồng nhau

MongoDB hỗ trợ tạo **index trên đường dẫn field lồng nhau**:

```javascript
db.customers.createIndex(
  { "profile.address.city": 1 },
  { name: "address_city_idx" }
)
```

Index này có thể hỗ trợ truy vấn lọc theo:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
})
```

Nếu thường lọc cả `city` và `district`, có thể cân nhắc compound index:

```javascript
db.customers.createIndex(
  {
    "profile.address.city": 1,
    "profile.address.district": 1
  },
  { name: "address_city_district_idx" }
)
```

Việc MongoDB thực sự sử dụng index nào còn phụ thuộc phân phối dữ liệu, độ chọn lọc, sort, projection và query planner. Kiểm tra kế hoạch truy vấn bằng:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội"
}).explain("executionStats")
```

Index trên **đường dẫn con** được xây dựng cho giá trị tại đường dẫn đó; không nên mặc định nó cung cấp cách thực thi giống hệt index trên **toàn embedded document**. Khi yêu cầu nghiệp vụ là equality nguyên object, hãy kiểm tra query shape và kế hoạch thực thi thực tế.

Nếu đường dẫn đi qua array, index có thể trở thành **multikey index**; những quy tắc dành cho multikey và compound multikey cần được xét riêng. Index giúp tăng tốc truy vấn phù hợp, nhưng không sửa được một bộ lọc sai ý nghĩa; ví dụ cần điều kiện cùng phần tử thì vẫn phải sử dụng `$elemMatch`.

## 13. Viết truy vấn tương đương bằng MongoDB Java Sync Driver

Khi ứng dụng Java truy cập MongoDB, MongoDB Java Sync Driver cho phép tạo bộ lọc bằng các helper như `Filters.eq()` và `Filters.elemMatch()`. Đường dẫn dot notation giữ nguyên.

Ví dụ:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.util.List;

public class NestedDocumentQueryDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("document_query_lab");
            MongoCollection<Document> customers =
                database.getCollection("customers");

            // 1. So sánh giá trị của field con
            System.out.println("Khách ở Hà Nội:");
            customers.find(Filters.eq("profile.address.city", "Hà Nội"))
                .forEach(doc -> System.out.println(doc.getString("_id")));

            // 2. So sánh toàn bộ embedded document
            Document address = new Document("city", "Hà Nội")
                .append("district", "Ba Đình")
                .append("zip", "100000");

            System.out.println("Address khớp chính xác:");
            customers.find(Filters.eq("profile.address", address))
                .forEach(doc -> System.out.println(doc.getString("_id")));

            // 3. Cùng một phần tử trong mảng orders
            System.out.println("Order A đã thanh toán:");
            customers.find(
                Filters.elemMatch(
                    "orders",
                    Filters.and(
                        Filters.eq("code", "A"),
                        Filters.eq("status", "paid")
                    )
                )
            ).forEach(doc -> System.out.println(doc.getString("_id")));
        }
    }
}
```

Cần khai báo dependency `mongodb-driver-sync` phù hợp với môi trường Java. Ví dụ giả định đã có dữ liệu mẫu và biến môi trường `MONGODB_URI` chứa connection string hợp lệ.

Với dữ liệu **chưa bị cập nhật**, kết quả theo các phần:

- Truy vấn dot notation theo `city`: `c101`, `c102`, `c103`.
- Equality nguyên `address`: chỉ `c101`, do object `Document` trong Java được dựng theo thứ tự `city` → `district` → `zip`.
- `elemMatch` order mã `A` và `paid`: chỉ `c103`.

Chương trình không áp đặt thứ tự in ra của các document nếu truy vấn không có `sort()`. Các tập ID dự kiến đúng về mặt nội dung, nhưng thứ tự dòng có thể khác.

### Lưu ý về thứ tự field khi dựng `Document` trong Java

Vì MongoDB equality nguyên embedded document nhạy với thứ tự field, hai object Java dưới đây không thể coi là tương đương đối với truy vấn equality nguyên object:

```java
Document a = new Document("city", "Hà Nội")
    .append("district", "Ba Đình")
    .append("zip", "100000");

Document b = new Document("district", "Ba Đình")
    .append("city", "Hà Nội")
    .append("zip", "100000");
```

Nếu mục tiêu là chỉ kiểm tra giá trị `city` và `district` mà không quan tâm thứ tự hoặc field khác, hãy dùng:

```java
Filters.and(
    Filters.eq("profile.address.city", "Hà Nội"),
    Filters.eq("profile.address.district", "Ba Đình")
)
```

Đây cũng là cách biểu đạt bền vững khi schema document có thể thêm field mới về sau.

## 14. Lỗi thường gặp khi truy vấn document lồng nhau

| Tình huống | Vì sao có lỗi hoặc kết quả bất ngờ? | Cách xử lý |
| --- | --- | --- |
| So sánh `profile.address` bằng object thiếu `zip` | Equality yêu cầu toàn bộ embedded document khớp | Truy vấn field con bằng dot notation nếu chỉ quan tâm vài field |
| Cùng giá trị nhưng đảo `city` và `district` lại không khớp | Equality embedded document nhạy thứ tự field | Dùng dot notation hoặc bảo đảm xây object đúng thứ tự khi thật sự cần equality toàn object |
| Thêm `note` vào `address` thì truy vấn cũ hết khớp | Document thực tế có field thừa so với object trong filter | Tránh equality nguyên object cho yêu cầu chỉ lọc theo các thuộc tính |
| Dùng `"orders.code":"A"` và `"orders.status":"paid"` nhưng khớp đơn chưa thanh toán | Hai điều kiện có thể thỏa ở hai phần tử mảng khác nhau | Dùng `$elemMatch` để ràng buộc cùng phần tử |
| `"profile.address": null` trả cả document không có address | Equality với `null` khớp giá trị null và field thiếu | Dùng `$type: "null"` hoặc `$exists` |
| Điều kiện theo `"orders.0.code"` bỏ sót order A ở vị trí khác | Bộ lọc phụ thuộc chỉ số của array | Dùng `"orders.code"` hoặc `$elemMatch` theo mục đích |
| Truy vấn `profile.address.city` không chạy như dự kiến trong JavaScript | Đường dẫn được viết như biểu thức thay vì tên khóa chuỗi | Viết `"profile.address.city"` trong filter |
| Kết quả projection có `profile: { address: {...} }` thay vì khóa phẳng | MongoDB giữ cấu trúc object lồng nhau | Truy cập giá trị qua đúng đường dẫn trên kết quả |
| Sau khi `$set` nguyên `profile.address`, các field khác biến mất | Lệnh update thay toàn bộ giá trị object | `$set` đúng đường dẫn field con nếu chỉ sửa một phần |
| Kết quả chạy với `find()` ở máy này có thứ tự khác máy khác | Truy vấn chưa yêu cầu sort | Thêm `.sort({_id: 1})` khi cần thứ tự xác định |

Một điểm bổ sung: dấu chấm trong **đường dẫn truy vấn** là ký pháp phân tách cấp object. Các trường hợp dùng **tên field thật sự chứa dấu chấm** (nếu dữ liệu được tạo ở phiên bản hỗ trợ) cần kỹ thuật truy cập khác, chẳng hạn `$getField` trong biểu thức aggregation. Đừng coi `"a.b"` là truy vấn tự động đến một field có tên nguyên văn `a.b` ở cấp gốc.

## 15. Bài tập và đáp án tham khảo

Các bài sau giả định collection `customers` vẫn giữ nguyên bộ dữ liệu ở mục 2.

### Bài 1. Tìm khách hàng theo một thuộc tính sâu

Yêu cầu: tìm khách hàng có `profile.address.district` bằng `"Ba Đình"`; chỉ trả về `name` và `profile.address.city`.

**Gợi ý lời giải:**

```javascript
db.customers.find(
  { "profile.address.district": "Ba Đình" },
  {
    _id: 0,
    name: 1,
    "profile.address.city": 1
  }
)
```

Kết quả về mặt tập document gồm `c101`, `c102`, `c103`.

### Bài 2. Phân tích vì sao hai filter cho kết quả khác nhau

```javascript
// Filter A
{ "profile.address.city": "Hà Nội" }

// Filter B
{
  "profile.address": {
    city: "Hà Nội",
    district: "Ba Đình",
    zip: "100000"
  }
}
```

Hỏi: Vì sao Filter A khớp `c102`, `c103` nhưng Filter B không?

**Đáp án:** Filter A chỉ so sánh giá trị `city` nên bỏ qua các field và thứ tự còn lại. Filter B yêu cầu equality nguyên object; `c102` có field `note` bổ sung, còn `c103` đặt `district` trước `city`.

### Bài 3. Phân biệt null và thiếu field

Yêu cầu: tìm customer có `profile.address` **tồn tại và có giá trị null**; sau đó tìm customer **thiếu** field `profile.address`.

**Đáp án:**

```javascript
// Field tồn tại và mang giá trị null
db.customers.find({
  "profile.address": { $type: "null" }
})

// Field không tồn tại
db.customers.find({
  "profile.address": { $exists: false }
})
```

Truy vấn đầu khớp `c105`; truy vấn sau khớp `c106`.

### Bài 4. Cùng đơn hàng hay hai đơn hàng khác nhau?

Yêu cầu: tìm khách hàng có **một đơn `A` đang `paid`**. Viết câu truy vấn và giải thích vì sao không dùng hai dot paths tách rời.

**Đáp án:**

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      status: "paid"
    }
  }
})
```

Kết quả là `c103`. Hai điều kiện dot notation `"orders.code": "A"` và `"orders.status": "paid"` có thể được thỏa bởi hai đơn hàng khác nhau trong cùng mảng.

### Bài 5. Nhiều cấp mảng lồng nhau

Yêu cầu: tìm khách hàng có đơn mã `A` chứa item mã `P-2` với `qty >= 2`.

**Đáp án:**

```javascript
db.customers.find({
  orders: {
    $elemMatch: {
      code: "A",
      items: {
        $elemMatch: {
          sku: "P-2",
          qty: { $gte: 2 }
        }
      }
    }
  }
})
```

Kết quả gồm `c101` trong bộ dữ liệu mẫu. `$elemMatch` ngoài giữ điều kiện trên cùng order; `$elemMatch` trong giữ hai điều kiện trên cùng item.

### Bài 6. Chọn thiết kế truy vấn theo yêu cầu

Một hệ thống giao hàng cần tìm tất cả khách có `city: "Hà Nội"` và `zip: "100000"`. Về sau, đối tượng `address` có thể bổ sung `building`, `floor`, `deliveryNote`. Nên dùng dot notation hay equality nguyên `address`?

**Đáp án:** Dùng dot notation vì nghiệp vụ chỉ quan tâm hai thuộc tính:

```javascript
db.customers.find({
  "profile.address.city": "Hà Nội",
  "profile.address.zip": "100000"
})
```

Truy vấn này không tự trở nên sai chỉ vì `address` có thêm những field khác.

## 16. Quy tắc ghi nhớ

Khi đọc hoặc viết truy vấn document lồng nhau, hãy đặt ba câu hỏi:

1. **Mình chỉ cần kiểm tra một số field con, hay cần object hoàn toàn giống nhau?** Nếu chỉ kiểm tra thuộc tính, dùng dot notation. Nếu toàn bộ embedded document là giá trị cần so sánh chính xác, dùng equality nguyên object và chú ý thứ tự field.
2. **Đường dẫn có đi qua array không?** Với một điều kiện đơn, dot notation thường đủ. Với nhiều điều kiện buộc cùng một phần tử mảng, dùng `$elemMatch`; khi có mảng lồng nhau, có thể cần nhiều lớp `$elemMatch`.
3. **Field có thể thiếu, null hoặc đổi kiểu không?** Nếu có, dùng `$exists`/`$type` để diễn đạt ý định rõ ràng; không coi equality với `null` là phép kiểm tra “chỉ có giá trị null”.

Hai biểu thức nhìn gần giống nhau có thể mang ý nghĩa khác biệt đáng kể trong MongoDB. Nắm chắc **đường dẫn field**, **equality nguyên embedded document**, **thứ tự field** và **ngữ nghĩa mảng** sẽ giúp truy vấn chính xác ngay cả khi cấu trúc document trở nên sâu và phức tạp hơn.
