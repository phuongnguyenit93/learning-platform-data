# Ràng buộc nhiều điều kiện trên cùng phần tử bằng `$elemMatch` trong MongoDB

MongoDB cho phép một document chứa mảng các giá trị đơn giản hoặc mảng các object lồng nhau. Khi truy vấn một mảng, câu hỏi quan trọng thường không chỉ là “document có giá trị này hay không?” mà còn là **“những điều kiện đó có cùng đúng trên một phần tử của mảng không?”**. Đây là mục đích chính của toán tử truy vấn `$elemMatch`.

Ví dụ một đơn hàng có dòng sản phẩm A với số lượng 1 và dòng sản phẩm B với số lượng 5. Hai điều kiện “có sản phẩm A” và “có số lượng ít nhất 3” đều đúng ở cấp document, nhưng **không có dòng hàng nào vừa là A vừa có số lượng ít nhất 3**. Nếu truy vấn sai, hệ thống có thể trả những đơn hàng không thỏa yêu cầu của người dùng.

Bài học thuộc chương **Truy vấn mảng** trong MongoDB. Ta sẽ giải thích chính xác ngữ nghĩa của `$elemMatch`, so sánh với dot notation, mở rộng sang mảng số, mảng object, object lồng nhau, mảng lồng nhau, projection, aggregation, cập nhật phần tử và index đa khóa (*multikey index*). Các ví dụ chạy trong **mongosh** trên database lab `elem_match_lab`.

## 1. Ý tưởng cốt lõi: “cùng document” khác “cùng phần tử”

Xét document:

~~~javascript
{
  _id: "order-001",
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 5 }
  ]
}
~~~

Truy vấn:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
})
~~~

có thể trả document trên vì:

- Điều kiện `"items.sku": "A"` khớp phần tử thứ nhất.
- Điều kiện `"items.qty": { $gte: 3 }` khớp phần tử thứ hai.

MongoDB đã thỏa **hai điều kiện ở cấp document**, nhưng chưa có ràng buộc buộc chúng cùng thuộc một item.

Để đòi hỏi **tồn tại ít nhất một item** vừa mang `sku = "A"` vừa có `qty >= 3`, dùng:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
})
~~~

Document `order-001` không khớp truy vấn này.

Về mặt logic:

~~~text
Không dùng $elemMatch:
  tồn tại item X có sku = "A"
  VÀ tồn tại item Y có qty >= 3
  X và Y có thể khác nhau.

Dùng $elemMatch:
  tồn tại item X sao cho
     X.sku = "A"
     VÀ X.qty >= 3
  Mọi điều kiện nằm trong cùng một phần tử X.
~~~

Có thể hình dung tương tự biểu thức `EXISTS` trong cơ sở dữ liệu quan hệ: tìm document khi tồn tại một phần tử mảng thỏa toàn bộ điều kiện ở bên trong.

## 2. Chuẩn bị bộ dữ liệu thực hành

Trong mongosh, chọn database riêng cho bài:

~~~javascript
use elem_match_lab
~~~

Thêm dữ liệu mẫu một lần:

~~~javascript
db.orders.insertMany([
  {
    _id: "ord-1",
    customerId: "c-01",
    status: "PAID",
    scores: [50, 98],
    items: [
      {
        sku: "A",
        qty: 1,
        price: 100,
        warehouse: "HCM",
        options: { color: "red", size: "M" },
        promotions: [{ code: "VIP", active: false }]
      },
      {
        sku: "B",
        qty: 5,
        price: 200,
        warehouse: "HN",
        options: { color: "blue", size: "L" },
        promotions: [{ code: "VIP", active: true }]
      }
    ]
  },
  {
    _id: "ord-2",
    customerId: "c-02",
    status: "PAID",
    scores: [82, 95],
    items: [
      {
        sku: "A",
        qty: 4,
        price: 150,
        warehouse: "HCM",
        options: { color: "red", size: "M" },
        promotions: [{ code: "VIP", active: true }]
      },
      {
        sku: "C",
        qty: 1,
        price: 300,
        warehouse: "HN",
        options: { color: "green", size: "S" },
        promotions: []
      }
    ]
  },
  {
    _id: "ord-3",
    customerId: "c-03",
    status: "CREATED",
    scores: [75, 88],
    items: [
      {
        sku: "A",
        qty: 2,
        price: 100,
        warehouse: "HN",
        options: { color: "blue", size: "M" },
        promotions: [{ code: "VIP", active: false }]
      },
      {
        sku: "B",
        qty: 4,
        price: 210,
        warehouse: "HCM",
        options: { color: "red", size: "L" },
        promotions: [{ code: "FLASH", active: true }]
      }
    ]
  },
  {
    _id: "ord-4",
    customerId: "c-04",
    status: "CREATED",
    scores: [],
    items: []
  },
  {
    _id: "ord-5",
    customerId: "c-05",
    status: "PAID",
    scores: [91, 96],
    items: [
      {
        sku: "B",
        qty: 7,
        price: 205,
        warehouse: "HCM",
        options: { color: "red", size: "M" },
        promotions: [{ code: "FLASH", active: false }]
      },
      {
        sku: "A",
        qty: 3,
        price: 155,
        warehouse: "HCM",
        options: { color: "blue", size: "S" },
        promotions: [{ code: "VIP", active: false }]
      }
    ]
  },
  {
    _id: "ord-6",
    customerId: "c-06",
    status: "PAID",
    scores: { midterm: 85 },
    items: {
      sku: "A",
      qty: 10,
      warehouse: "HCM"
    }
  }
])
~~~

**Lưu ý thực hành:** `ord-6` cố ý có `items` là **object đơn thay vì mảng** và `scores` là object, để minh họa khác biệt ngữ nghĩa khi schema không đồng nhất. Trong một hệ thống thật, nên áp dụng schema validation để tránh dữ liệu sai hình dạng. Chạy lại `insertMany()` với cùng `_id` sẽ gây lỗi duplicate key; có thể dùng database lab mới nếu cần thử lại, thay vì xóa dữ liệu không thuộc phạm vi thực hành.

Bảng rút gọn:

| Đơn | Các item chính | `scores` | Vai trò trong bài |
|---|---|---|---|
| `ord-1` | A:1 tại HCM; B:5 tại HN | `[50,98]` | Có điều kiện trên hai item khác nhau |
| `ord-2` | A:4 tại HCM; C:1 tại HN | `[82,95]` | Có A đủ số lượng, VIP active trên A |
| `ord-3` | A:2 tại HN; B:4 tại HCM | `[75,88]` | A và qty lớn thuộc hai item khác nhau |
| `ord-4` | Mảng rỗng | `[]` | Không có phần tử để khớp |
| `ord-5` | B:7 tại HCM; A:3 tại HCM | `[91,96]` | Có A đủ số lượng; nhiều item đủ qty |
| `ord-6` | Object A:10, không phải mảng | Object | Phân biệt dot notation và `$elemMatch` |

Để xem danh sách ID gọn, sử dụng projection và sort:

~~~javascript
db.orders.find(
  { status: "PAID" },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Phần lớn ví dụ sẽ dùng `{_id: 1}` để kết quả dễ đối chiếu mà không phải đọc lại toàn bộ document.

## 3. Dot notation có thể ghép điều kiện từ nhiều phần tử

### 3.1. Truy vấn chỉ dùng dot notation

~~~javascript
db.orders.find(
  {
    "items.sku": "A",
    "items.qty": { $gte: 3 }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Với dữ liệu mẫu, các ID khớp gồm:

~~~text
ord-1
ord-2
ord-3
ord-5
ord-6
~~~

Giải thích:

- `ord-1`: A có qty 1, nhưng B có qty 5; hai điều kiện được đáp ứng bởi hai item.
- `ord-2`: A có qty 4; cả hai điều kiện đúng ngay trên A.
- `ord-3`: A có qty 2, nhưng B có qty 4; lại là hai item.
- `ord-5`: A có qty 3; cùng phần tử.
- `ord-6`: `items` là object đơn chứa `sku: "A"` và `qty: 10`; dot notation vẫn truy cập được các field con của object.

Mục đích của dot notation là truy cập field lồng nhau và cho phép MongoDB tìm match trong mảng. Nó **không mặc định nhóm tất cả predicate về một phần tử**.

### 3.2. Thêm `$and` bên ngoài không sửa được lỗi

~~~javascript
db.orders.find({
  $and: [
    { "items.sku": "A" },
    { "items.qty": { $gte: 3 } }
  ]
})
~~~

Hai nhánh của `$and` vẫn được đánh giá trên document; mỗi nhánh có thể khớp một phần tử khác nhau. `$and` chỉ yêu cầu cả hai điều kiện đúng, **không thêm ràng buộc đồng nhất phần tử**.

### 3.3. Dùng `$elemMatch` để ràng buộc đúng

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Kết quả:

~~~text
ord-2
ord-5
~~~

`ord-1` và `ord-3` không còn khớp vì A của chúng có `qty` nhỏ hơn 3; `ord-6` không khớp vì `items` không phải mảng.

### 3.4. Cú pháp tổng quát

~~~javascript
db.collection.find({
  arrayField: {
    $elemMatch: {
      field1: condition1,
      field2: condition2,
      field3: condition3
    }
  }
})
~~~

Ý nghĩa: một document được chọn khi `arrayField` là mảng có **ít nhất một phần tử** thỏa đồng thời mọi predicate bên trong `$elemMatch`. Với mảng object, ta dùng tên field tương đối với từng object phần tử; với mảng scalar, dùng trực tiếp toán tử so sánh.

## 4. `$elemMatch` với mảng số hoặc chuỗi

`$elemMatch` không chỉ dành cho mảng object. Nó đặc biệt quan trọng khi có **nhiều điều kiện khoảng giá trị** trên cùng một phần tử.

### 4.1. Đòi hỏi một điểm số nằm trong khoảng

Bài toán: tìm đơn có **ít nhất một** score thỏa:

~~~text
80 <= score < 90
~~~

Truy vấn dễ nhầm:

~~~javascript
db.orders.find(
  {
    scores: {
      $gte: 80,
      $lt: 90
    }
  },
  { _id: 1, scores: 1 }
).sort({ _id: 1 })
~~~

Với mảng, điều kiện `$gte` có thể khớp một score và `$lt` khớp một score khác. Ví dụ `ord-1` có `[50, 98]`: 98 ≥ 80, còn 50 < 90, nhưng **không có score nào nằm trong khoảng**.

Truy vấn đúng:

~~~javascript
db.orders.find(
  {
    scores: {
      $elemMatch: {
        $gte: 80,
        $lt: 90
      }
    }
  },
  { _id: 1, scores: 1 }
).sort({ _id: 1 })
~~~

Kết quả:

~~~text
ord-2  scores: [82, 95]  -> 82 nằm trong khoảng.
ord-3  scores: [75, 88]  -> 88 nằm trong khoảng.
~~~

`ord-1` bị loại vì không phần tử nào thỏa cả hai điều kiện. `ord-5` có `[91, 96]` nên không có score nhỏ hơn 90; `ord-4` rỗng; `ord-6` là object thay vì mảng.

### 4.2. Nhiều điều kiện trên một giá trị primitive

~~~javascript
// Tồn tại một phần tử mảng ratings có giá trị trong [4, 5).
db.products.find({
  ratings: {
    $elemMatch: {
      $gte: 4,
      $lt: 5
    }
  }
})
~~~

Với mảng chuỗi:

~~~javascript
// Tồn tại một phần tử code nằm trong tập hợp cụ thể.
db.catalog.find({
  codes: {
    $elemMatch: {
      $in: ["A-100", "A-200"]
    }
  }
})
~~~

Với **một điều kiện đơn lẻ** trên mảng scalar, `$elemMatch` thường không cần thiết để ràng buộc cùng phần tử, vì chỉ có một predicate. Tuy vậy, `$elemMatch` vẫn buộc field phải là **mảng**; đây có thể là khác biệt khi schema có document chứa scalar hoặc object thay vì array.

### 4.3. Kiểu dữ liệu vẫn quan trọng

Giá trị `"85"` là chuỗi khác với số `85`. Điều kiện range dùng quy tắc so sánh BSON và type của MongoDB; không nên mong MongoDB tự chuyển mọi chuỗi số thành số. Khi dữ liệu có kiểu hỗn hợp, hãy chuẩn hóa schema và dùng validator phù hợp trước khi tin kết quả truy vấn.

## 5. `$elemMatch` với mảng object: ba hoặc nhiều điều kiện

### 5.1. Cùng SKU, số lượng và kho

Bài toán: tìm đơn có **một item A**, số lượng từ 3 trở lên, được xuất từ kho HCM.

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 },
        warehouse: "HCM"
      }
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Kết quả:

~~~text
ord-2
ord-5
~~~

Trong `ord-3` có A và có một item số lượng 4 tại HCM, nhưng item số lượng 4 là B, nên không khớp.

### 5.2. Kết hợp equality, range, membership

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $in: ["A", "C"] },
      qty: { $gte: 2, $lte: 5 },
      warehouse: "HCM"
    }
  }
})
~~~

Một item phải có SKU thuộc tập A/C, số lượng nằm trong `[2, 5]` và kho HCM. `$in`, `$gte`, `$lte` đều áp dụng trên **field của cùng item** vì nằm trong một `$elemMatch`.

### 5.3. Điều kiện lồng nhau trong object của item

Mỗi item có object `options`. Tìm item A, qty ≥ 3, màu đỏ, size M:

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 },
        "options.color": "red",
        "options.size": "M"
      }
    }
  },
  { _id: 1 }
)
~~~

Kết quả là `ord-2`. Dot notation **bên trong `$elemMatch`** như `"options.color"` truy cập object con của **cùng item đang xét**.

Không nhầm hai tầng:

~~~javascript
// Có thể dùng item khác nhau: không đảm bảo cùng item.
{
  "items.sku": "A",
  "items.options.color": "red"
}

// Bắt buộc cùng một item có A và màu đỏ.
{
  items: {
    $elemMatch: {
      sku: "A",
      "options.color": "red"
    }
  }
}
~~~

## 6. Một điều kiện trong `$elemMatch` vẫn có ý nghĩa

Theo cú pháp, `$elemMatch` không bắt buộc phải có ít nhất hai predicate. Ví dụ:

~~~javascript
db.orders.find(
  { "items.sku": "A" },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Trả `ord-1`, `ord-2`, `ord-3`, `ord-5` và `ord-6`. Còn:

~~~javascript
db.orders.find(
  { items: { $elemMatch: { sku: "A" } } },
  { _id: 1 }
).sort({ _id: 1 })
~~~

chỉ trả `ord-1`, `ord-2`, `ord-3` và `ord-5`, vì `ord-6.items` là object đơn.

Vậy `$elemMatch` còn có đặc điểm **chỉ tìm trên field có dạng array**. Nếu dữ liệu tuân thủ schema luôn là mảng, sự khác biệt trên thường không ảnh hưởng với một predicate. Nếu dữ liệu hỗn hợp, khác biệt có thể làm API trả kết quả khác.

Điều này cũng nhắc rằng **truy vấn không thay thế schema validation**. Nếu nghiệp vụ yêu cầu `items` luôn là array, hãy thiết kế validator để tránh trường hợp `ord-6` có trong dữ liệu production.

## 7. Mảng lồng nhau: `$elemMatch` ở nhiều cấp

Một item có thể chứa mảng `promotions`. Bài toán: tìm đơn có **item A số lượng ít nhất 3**, và **chính item A đó** có promotion VIP đang active.

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 },
        promotions: {
          $elemMatch: {
            code: "VIP",
            active: true
          }
        }
      }
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Kết quả:

~~~text
ord-2
~~~

Giải thích:

- `ord-1` có item B được VIP active, còn item A chỉ qty 1 và VIP inactive.
- `ord-2` có item A qty 4 và VIP active.
- `ord-3` có item A qty 2, VIP inactive; item B có FLASH.
- `ord-5` có item A qty 3 nhưng VIP inactive.

**Hai cấp `$elemMatch` ràng buộc hai cấp phần tử khác nhau**: một item của `items`, rồi một promotion của `promotions` thuộc chính item ấy.

~~~mermaid
flowchart TD
    O["Document order"] --> I["Tồn tại item trong items"]
    I --> S["item.sku = A"]
    I --> Q["item.qty >= 3"]
    I --> P["Tồn tại promotion trong item.promotions"]
    P --> C["promotion.code = VIP"]
    P --> A["promotion.active = true"]
~~~

Một pattern tương tự xuất hiện ở:

- `departments[].employees[]`: cùng phòng ban, cùng nhân viên có role và trạng thái.
- `shipments[].packages[]`: cùng chuyến giao, cùng kiện hàng có loại và trọng lượng.
- `courses[].lessons[]`: cùng khóa học, cùng bài có loại và mức độ khó.
- `bookings[].guests[]`: cùng booking, một khách thỏa các thuộc tính liên quan.

### Ví dụ riêng với hai mảng lồng nhau

~~~javascript
db.teams.insertOne({
  _id: "team-1",
  groups: [
    {
      name: "operations",
      members: [
        { userId: "u-1", role: "viewer", active: true },
        { userId: "u-2", role: "admin", active: false }
      ]
    },
    {
      name: "engineering",
      members: [
        { userId: "u-3", role: "admin", active: true }
      ]
    }
  ]
})
~~~

Truy vấn này **không khớp** `team-1`:

~~~javascript
db.teams.find({
  groups: {
    $elemMatch: {
      name: "operations",
      members: {
        $elemMatch: {
          role: "admin",
          active: true
        }
      }
    }
  }
})
~~~

Vì nhóm operations không có **một member** vừa admin vừa active. Admin active nằm ở engineering. Nếu chỉ dùng các dotted field cấp document, rất dễ vô tình ghép thuộc tính của những nhóm hoặc thành viên khác nhau.

## 8. Khi cần hai phần tử khác nhau thỏa hai tập điều kiện

`$elemMatch` đơn mô tả:

> Tồn tại **một phần tử** thỏa **tất cả** điều kiện.

Nhưng một số yêu cầu là:

> Tồn tại một item A với qty ≥ 2 **và** tồn tại một item B với qty ≥ 4 trong **cùng đơn hàng**.

Đây là hai phần tử có thể khác nhau. Không thể viết `sku: "A"` và `sku: "B"` bên trong cùng một `$elemMatch`, vì một field SKU đơn trị không thể đồng thời bằng A và B.

### 8.1. Kết hợp `$all` với nhiều `$elemMatch`

~~~javascript
db.orders.find(
  {
    items: {
      $all: [
        { $elemMatch: { sku: "A", qty: { $gte: 2 } } },
        { $elemMatch: { sku: "B", qty: { $gte: 4 } } }
      ]
    }
  },
  { _id: 1 }
).sort({ _id: 1 })
~~~

Kết quả:

~~~text
ord-3
ord-5
~~~

`ord-3` có A:2 và B:4; `ord-5` có A:3 và B:7. Trong mỗi nhóm điều kiện, `$elemMatch` giữ đúng cùng phần tử; `$all` yêu cầu cả hai nhóm điều kiện cùng được thỏa trong mảng.

### 8.2. Lưu ý về “hai phần tử khác nhau”

Hai `$elemMatch` riêng **không mặc nhiên bắt buộc hai phần tử có chỉ số khác nhau**. Nếu điều kiện của hai nhóm chồng lấn, **cùng một phần tử có thể thỏa cả hai**. Ở ví dụ A/B, vì một item có một SKU đơn trị, item A và item B tự nhiên phải khác nhau.

Nếu bài toán bắt buộc hai phần tử phân biệt nhưng chúng có thể cùng giá trị thuộc tính, cần mô hình có định danh phần tử, logic aggregation phù hợp hoặc xử lý tập kết quả để kiểm tra distinctness. Không suy diễn `$all + $elemMatch` tự đếm số phần tử khác nhau.

### 8.3. Khác với đặt hai `$elemMatch` trong `$and`

~~~javascript
db.orders.find({
  $and: [
    { items: { $elemMatch: { sku: "A", qty: { $gte: 2 } } } },
    { items: { $elemMatch: { sku: "B", qty: { $gte: 4 } } } }
  ]
})
~~~

Về ý nghĩa nghiệp vụ trên, biểu thức này cũng yêu cầu hai điều kiện tồn tại riêng trong mảng. `$all` với nhiều `$elemMatch` là một cách biểu đạt trực tiếp theo operator mảng; `$and` có thể hữu ích khi ghép nhiều nhánh logic khác.

**Không dùng một object JavaScript có hai khóa `items` trùng tên**:

~~~javascript
// SAI: trong object JavaScript, khóa thứ hai có thể ghi đè khóa thứ nhất.
{
  items: { $elemMatch: { sku: "A" } },
  items: { $elemMatch: { sku: "B" } }
}
~~~

Một object không nên chứa các khóa trùng để biểu thị hai điều kiện; dùng `$and` hoặc `$all` đúng cú pháp.

## 9. Mảng rỗng, field thiếu và toán tử phủ định

### 9.1. `$elemMatch` có nghĩa “tồn tại”

Với:

~~~javascript
{ items: [] }
~~~

không tồn tại phần tử nào để thỏa predicate. Vì vậy truy vấn `items: {$elemMatch: {...}}` không khớp mảng rỗng.

Nếu field `items` vắng mặt hoặc là object đơn thay vì mảng, `$elemMatch` cũng không khớp. Trong thực tế phải xét schema: field thiếu có thể hợp lệ cho document legacy, hoặc là lỗi dữ liệu cần sửa.

### 9.2. `$ne` bên ngoài và bên trong `$elemMatch` khác nhau

So sánh hai ý định:

**Ý định A: không có item nào có SKU A.**

~~~javascript
db.orders.find({
  "items.sku": { $ne: "A" }
})
~~~

Với MongoDB, điều kiện `$ne` trên đường dẫn mảng thường khớp khi **không có giá trị SKU A** (và có thể khớp document thiếu field liên quan). Không nên đọc nó như “có ít nhất một item khác A”.

**Ý định B: tồn tại ít nhất một item có SKU khác A.**

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $ne: "A" }
    }
  }
})
~~~

Document `ord-1` có A và B:

- Ý định A: **không khớp** vì có A.
- Ý định B: **khớp** vì có B khác A.

Ngoài ra, `{sku: {$ne: "A"}}` có thể thỏa trên phần tử **thiếu field `sku`**. Nếu nghiệp vụ yêu cầu SKU tồn tại và khác A, hãy bổ sung điều kiện tồn tại/kiểu giá trị thích hợp.

### 9.3. Muốn đảm bảo “không tồn tại phần tử vi phạm”

Có thể diễn đạt bằng phủ định trên điều kiện tồn tại:

~~~javascript
// Không có item nào có qty âm.
db.orders.find({
  $nor: [
    {
      items: {
        $elemMatch: {
          qty: { $lt: 0 }
        }
      }
    }
  ]
})
~~~

Lệnh này cũng có thể khớp document mà `items` thiếu, rỗng hoặc không phải mảng, bởi trên chúng không tồn tại item có qty âm. Nếu cần **vừa là mảng hợp lệ, vừa không có phần tử vi phạm**, thêm validation cho dữ liệu hoặc điều kiện kiểu mảng phù hợp:

~~~javascript
db.orders.find({
  $and: [
    { items: { $type: "array" } },
    {
      $nor: [
        { items: { $elemMatch: { qty: { $lt: 0 } } } }
      ]
    }
  ]
})
~~~

`$elemMatch` biểu diễn lượng từ “**tồn tại**”; điều kiện “**mọi phần tử đều thỏa**” thường được mô hình hóa thành “không tồn tại phần tử nào vi phạm”, đồng thời phải xét mảng rỗng và tính hợp lệ của schema.

### 9.4. `null` và field thiếu

Với các điều kiện như `field: null`, MongoDB có ngữ nghĩa bao gồm cả field `null` và trong nhiều ngữ cảnh cả field bị thiếu. Vì vậy:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      discountCode: null
    }
  }
})
~~~

có thể trả những item A không có field `discountCode`, chứ không chỉ item gán explicit BSON null. Nếu cần phân biệt, thiết kế schema nhất quán và dùng `$exists`, `$type` hoặc điều kiện rõ ràng khác. Không lấy kết quả một ví dụ nhỏ để suy diễn chung cho mọi kiểu BSON.

## 10. `$elemMatch` ở query khác `$elemMatch` ở projection

Đây là khác biệt rất dễ gây hiểu lầm.

### 10.1. `$elemMatch` trong filter chọn **document**

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  }
)
~~~

Mặc định MongoDB trả document khớp với **toàn bộ mảng `items`**. `$elemMatch` trong filter **không tự loại bỏ các item còn lại** khỏi document trả về.

Ví dụ `ord-5` khớp vì có item A:3, nhưng nếu không dùng projection, kết quả vẫn chứa cả item B:7 và A:3.

### 10.2. `$elemMatch` ở projection chỉ trả phần tử khớp đầu tiên

~~~javascript
db.orders.find(
  { _id: "ord-5" },
  {
    _id: 1,
    items: {
      $elemMatch: { qty: { $gte: 3 } }
    }
  }
)
~~~

`ord-5` có cả B:7 và A:3 đủ điều kiện. Nhưng projection `$elemMatch` chỉ đưa **phần tử đầu tiên** trong thứ tự mảng thỏa `qty >= 3` vào mảng kết quả. Ở dữ liệu mẫu, đó là B:7.

Nếu muốn tìm đơn có A:3 và đồng thời chỉ hiển thị item A đó:

~~~javascript
db.orders.find(
  {
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  },
  {
    _id: 1,
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  }
)
~~~

Ở đây có **hai lần xuất hiện** của `$elemMatch` với vai trò khác nhau:

- Trong **filter**: chọn document có ít nhất một item phù hợp.
- Trong **projection**: chỉ giữ phần tử phù hợp đầu tiên của `items` trong document được trả về.

Đừng giả định điều kiện của projection tự được áp dụng vào filter; nếu chúng khác nhau, kết quả cũng có thể khác nhau.

### 10.3. Nếu cần tất cả phần tử khớp: dùng `$filter`

Projection `$elemMatch` không trả toàn bộ các item khớp. Dùng aggregation `$filter`:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-5" } },
  {
    $project: {
      _id: 1,
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $gte: ["$$item.qty", 3]
          }
        }
      }
    }
  }
])
~~~

Kết quả `eligibleItems` chứa **cả B:7 và A:3**, theo thứ tự ban đầu. Có thể kết hợp nhiều điều kiện cùng phần tử:

~~~javascript
db.orders.aggregate([
  { $match: { _id: { $in: ["ord-2", "ord-5"] } } },
  {
    $project: {
      eligibleItems: {
        $filter: {
          input: "$items",
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.sku", "A"] },
              { $gte: ["$$item.qty", 3] }
            ]
          }
        }
      }
    }
  }
])
~~~

Trong `$filter`, điều kiện `$$item.sku` và `$$item.qty` cùng tham chiếu phần tử có tên biến `item`, nên cũng bảo đảm cùng phần tử. Cần lưu ý `$filter` yêu cầu input là array (hoặc null/missing theo quy tắc của aggregation); nếu schema có object sai kiểu như `ord-6.items`, pipeline cần xử lý kiểu trước hoặc không chọn document đó.

Một cách phòng vệ khi dữ liệu có kiểu hỗn hợp:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      eligibleItems: {
        $filter: {
          input: {
            $cond: [
              { $isArray: "$items" },
              "$items",
              []
            ]
          },
          as: "item",
          cond: {
            $and: [
              { $eq: ["$$item.sku", "A"] },
              { $gte: ["$$item.qty", 3] }
            ]
          }
        }
      }
    }
  }
])
~~~

Đó là cơ chế tránh lỗi khi đọc dữ liệu legacy; với hệ thống mới, nên giải quyết nguyên nhân ở schema và lúc ghi dữ liệu.

## 11. Dùng `$unwind` khi cần xử lý từng phần tử như một dòng

Nếu cần thống kê, group hoặc trả từng item thành record riêng, aggregation `$unwind` biến các phần tử mảng thành những document trung gian.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: { $in: ["ord-1", "ord-2", "ord-3", "ord-5"] }
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "A",
      "items.qty": { $gte: 3 }
    }
  },
  {
    $project: {
      _id: 1,
      sku: "$items.sku",
      qty: "$items.qty",
      warehouse: "$items.warehouse"
    }
  }
])
~~~

Sau `$unwind`, mỗi document trung gian biểu diễn **một item**, vì vậy hai predicate trên `items.sku` và `items.qty` của stage `$match` sau đó cùng áp dụng vào item hiện tại. Kết quả gồm item A:4 của `ord-2` và A:3 của `ord-5`.

### Cẩn thận với thứ tự pipeline

Đoạn sau có thể bị lỗi ngữ nghĩa:

~~~javascript
// Dễ nhầm: match trước unwind cho phép các item khác nhau đáp ứng.
db.orders.aggregate([
  {
    $match: {
      "items.sku": "A",
      "items.qty": { $gte: 3 }
    }
  },
  { $unwind: "$items" }
])
~~~

Stage `$match` đầu chọn cả `ord-1` và `ord-3` vì ghép hai item khác nhau. Sau `$unwind`, pipeline còn có thể đưa các item không hợp lệ sang stage tiếp theo nếu không lọc lại.

Cách thực hiện tốt hơn khi cần tối ưu lọc sớm:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      items: {
        $elemMatch: {
          sku: "A",
          qty: { $gte: 3 }
        }
      }
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      "items.sku": "A",
      "items.qty": { $gte: 3 }
    }
  }
])
~~~

Stage đầu chọn đúng document có item thỏa toàn bộ điều kiện; stage sau `$unwind` giữ đúng item. Khi thiết kế pipeline, xác định rõ mỗi stage đang xử lý **document nguyên mảng** hay **một phần tử đã được tách**.

## 12. Index đa khóa và `$elemMatch`

MongoDB có thể sử dụng **multikey index** khi field được index chứa mảng. Khi index các field trong mảng object, mỗi phần tử có thể đóng góp key cho index. Nhưng multikey index **không tự sửa một truy vấn sai ngữ nghĩa**: nếu predicate được viết tách rời, query vẫn có thể cho phép chúng khớp các phần tử khác nhau.

### 12.1. Index cho query trên item

Giả sử workload thường tìm các đơn có item theo SKU và số lượng:

~~~javascript
db.orders.createIndex(
  {
    "items.sku": 1,
    "items.qty": 1
  },
  { name: "idx_items_sku_qty" }
)
~~~

Đây là compound multikey index trên hai field xuất phát từ cùng mảng `items`. Mục tiêu là hỗ trợ những truy vấn lọc theo SKU và qty của item.

Truy vấn:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}).explain("executionStats")
~~~

Trong những điều kiện phù hợp, `$elemMatch` giúp query planner **kết hợp giới hạn index** từ hai predicate trên cùng một phần tử mảng, giảm việc quét những key không liên quan. Cách kết hợp phụ thuộc **index key path chung, query shape và quy tắc multikey bounds**; không được mặc định mọi compound index đều dùng được mọi bound.

### 12.2. Vì sao `$elemMatch` còn quan trọng cho optimizer?

Nếu viết:

~~~javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 3 }
})
~~~

query có ngữ nghĩa “hai phần tử có thể khác nhau”. Engine phải giữ đúng ngữ nghĩa đó, nên không được tùy tiện thu hẹp tập kết quả bằng cách giả định cả hai điều kiện cùng đúng trên một phần tử. Với query dùng `$elemMatch`, ràng buộc same-element đã được khai báo rõ, tạo cơ hội cho planner khai thác compound multikey index tốt hơn.

**Hai lợi ích tách biệt:**

1. **Correctness:** loại những document chỉ ghép điều kiện từ các item khác nhau.
2. **Potential performance:** cung cấp điều kiện cho index bound compounding hoặc lọc sớm phù hợp.

Lợi ích hiệu năng cần được đo; không bảo đảm mọi query dùng `$elemMatch` đều nhanh hơn query khác trong mọi tập dữ liệu.

### 12.3. Đọc kết quả `explain`

~~~javascript
const plan = db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}).explain("executionStats")

printjson(plan.queryPlanner.winningPlan)
printjson(plan.executionStats)
~~~

Các trường thường quan sát:

| Trường | Ý nghĩa cơ bản |
|---|---|
| `winningPlan` | Kế hoạch truy vấn được chọn |
| `IXSCAN` | Một stage đọc key từ index |
| `COLLSCAN` | Một stage quét collection |
| `FETCH` | Lấy document và có thể tiếp tục kiểm tra predicate |
| `totalKeysExamined` | Số index key đã kiểm tra |
| `totalDocsExamined` | Số document đã kiểm tra |
| `nReturned` | Số document trả về |

Một tập dữ liệu chỉ có sáu document quá nhỏ để đánh giá hiệu năng: query planner có thể chọn `COLLSCAN` dù có index hợp lệ. Dùng dữ liệu đại diện, cùng filter/sort/projection, thu số đo trước và sau khi tạo index, đồng thời đo chi phí duy trì index khi ghi.

### 12.4. Hạn chế của compound multikey index

Không thể vô tư đưa nhiều field mảng **độc lập** vào cùng một compound index; MongoDB có giới hạn đối với các compound multikey index chứa các đường dẫn mảng khác nhau. Trường hợp nhiều field con của **cùng mảng embedded document** như `items.sku` và `items.qty` là mô hình cần phân biệt với các field từ hai mảng độc lập, chẳng hạn `items[]` và `coupons[]`.

Thứ tự field index còn phải dựa vào equality, range, sort và phân bố dữ liệu. Không tạo hàng loạt index chỉ vì query có nhiều điều kiện; mỗi index tăng dung lượng và chi phí ghi.

## 13. `$elemMatch` và thao tác cập nhật phần tử

`$elemMatch` là toán tử **truy vấn**. Nó chọn document thỏa điều kiện; bản thân nó không tự cập nhật phần tử. Khi cần sửa chính item phù hợp, kết hợp với toán tử cập nhật mảng.

### 13.1. Cập nhật item đầu tiên khớp bằng positional `$`

Ví dụ đánh dấu item A có qty ≥ 3 của `ord-2`:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-2",
    items: {
      $elemMatch: {
        sku: "A",
        qty: { $gte: 3 }
      }
    }
  },
  {
    $set: { "items.$.reviewed": true }
  }
)
~~~

Positional `$` trong đường dẫn update tham chiếu phần tử mảng được match qua điều kiện truy vấn theo quy tắc toán tử này. Ví dụ có mục tiêu đơn giản: một item A hợp lệ. Trong các query có nhiều mảng hoặc ràng buộc phức tạp, positional `$` có giới hạn và có thể dễ gây nhầm; nên xem `arrayFilters` khi cần xác định chính xác nhiều phần tử.

### 13.2. Dùng `arrayFilters` để chọn phần tử phải cập nhật

~~~javascript
db.orders.updateOne(
  { _id: "ord-5" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "A",
        "line.qty": { $gte: 3 }
      }
    ]
  }
)
~~~

Ở đây `line` là một biến đại diện cho phần tử của `items`. Hai điều kiện `line.sku` và `line.qty` trong cùng một array filter áp dụng cho **một item**. Cấu trúc cập nhật `$[line]` có thể nhắm đến mọi phần tử thỏa bộ lọc, khác với positional `$` thường nhắm phần tử match đầu tiên.

**Phân biệt ba vai trò:**

- `$elemMatch` ở filter: document nào đủ điều kiện được xử lý?
- Positional `$` hoặc `$[line]` trong update path: phần tử nào được sửa?
- `arrayFilters`: ràng buộc đối với phần tử ứng với identifier trong update path.

Nếu chỉ query `{items: {$elemMatch: {...}}}` nhưng dùng `$set: {status: "UPDATED"}`, bạn chỉ thay field `status` cấp document; các item không tự bị sửa.

### 13.3. Cần tính đúng khi có concurrent update

Trong xử lý đơn hàng thật, chỉ kiểm tra `qty >= 3` trước khi cập nhật chưa đủ cho các nghiệp vụ có nhiều request cạnh tranh. Nếu update liên quan tồn kho hoặc số tiền, dùng điều kiện nguyên tử phù hợp, kiểm tra `matchedCount/modifiedCount` và thiết kế transaction khi cần thay nhiều document cùng lúc. `$elemMatch` giải quyết **ngữ nghĩa cùng phần tử**, không tự giải quyết concurrency giữa các request.

## 14. Truy vấn mảng trong Java driver

Khi ứng dụng viết bằng Java, MongoDB Java Driver cung cấp builders tương đương. Ví dụ sau giả định biến `database` là `MongoDatabase` đã được tạo từ một `MongoClient` phù hợp:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

MongoCollection<Document> orders = database.getCollection("orders");

Bson filter = Filters.elemMatch(
    "items",
    Filters.and(
        Filters.eq("sku", "A"),
        Filters.gte("qty", 3),
        Filters.eq("warehouse", "HCM")
    )
);

for (Document order : orders.find(filter)) {
    System.out.println(order.getString("_id"));
}
~~~

Lưu ý điều kiện bên trong `Filters.elemMatch("items", ...)` dùng các field **`sku`, `qty`, `warehouse` của item**, thay vì tự thêm prefix `items.` vào mỗi field. Đây là phần tương ứng với:

~~~javascript
{
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      warehouse: "HCM"
    }
  }
}
~~~

Trong Spring Data MongoDB, API xây dựng query khác Java Driver trực tiếp nhưng mục tiêu tương đương. Hãy bảo đảm DSL bạn dùng tạo ra bộ lọc MongoDB có `$elemMatch` tại đúng array path, thay vì chỉ ghép hai điều kiện dotted field độc lập. Không cần phụ thuộc một framework cụ thể mới hiểu được ngữ nghĩa.

## 15. Thiết kế schema để `$elemMatch` dễ dùng và đáng tin cậy

Một query đúng vẫn có thể khó bảo trì nếu document chứa những mảng quá lớn, phần tử không đồng nhất hoặc dữ liệu nested thiếu quy ước.

### 15.1. Mỗi phần tử nên là một đơn vị nghiệp vụ rõ ràng

Ví dụ item đơn hàng:

~~~javascript
{
  sku: "A",
  qty: 4,
  price: NumberDecimal("150000.00"),
  warehouse: "HCM"
}
~~~

Nếu `sku` và `qty` đều là thuộc tính của một item, đặt chúng trong **cùng object phần tử** giúp ứng dụng có thể truy vấn và cập nhật nguyên tử ở mức document, đồng thời dễ biểu đạt điều kiện same-element.

### 15.2. Tránh mảng song song

Anti-pattern:

~~~javascript
{
  skus: ["A", "B"],
  quantities: [1, 5]
}
~~~

Ứng dụng phải hiểu rằng index 0 trong `skus` tương ứng index 0 trong `quantities`. `$elemMatch` trên `skus` không thể ràng buộc trực tiếp giá trị tại cùng vị trí của mảng `quantities` độc lập. Khi một mảng bị thêm/xóa phần tử lệch nhau, dữ liệu có thể mất tương quan.

Mô hình rõ hơn:

~~~javascript
{
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 5 }
  ]
}
~~~

### 15.3. Giới hạn kích thước mảng

Một BSON document có giới hạn 16 MiB. Nếu `items`, `events` hay `measurements` tăng vô hạn, việc nhúng toàn bộ vào một document có thể làm truy vấn/cập nhật nặng và đụng giới hạn kích thước. Với mảng có tăng trưởng lớn, cân nhắc tách collection con, bucket pattern có giới hạn hoặc mô hình lưu thời gian phù hợp.

### 15.4. Validation giúp kết quả ổn định

Ví dụ collection mới yêu cầu `items` luôn là array; mỗi item là object có `sku` là string và `qty` là số nguyên không âm:

~~~javascript
db.createCollection("orders_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["items"],
      properties: {
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["sku", "qty"],
            properties: {
              sku: { bsonType: "string", minLength: 1 },
              qty: {
                bsonType: ["int", "long"],
                minimum: 0
              }
            }
          }
        }
      }
    }
  },
  validationAction: "error"
})
~~~

Đây là collection **khác** với `orders` chứa dữ liệu demo (vốn cố ý có `ord-6` sai kiểu). Trong ứng dụng, BSON numeric type phải phù hợp với cách driver ghi dữ liệu. Validator cũng cần xét có cho mảng rỗng hay không, có bắt buộc unique SKU trong mảng hay không, và chính sách schema migration.

## 16. Khi nào `$elemMatch` không phải công cụ chính?

Không nên dùng `$elemMatch` cho mọi câu hỏi về mảng chỉ vì dữ liệu chứa array.

| Bài toán | Công cụ chính | Lý do |
|---|---|---|
| Có một item đáp ứng nhiều điều kiện | Query `$elemMatch` | Bảo đảm cùng phần tử |
| Có một giá trị trong mảng | So sánh trực tiếp, `$in` hoặc `$elemMatch` tùy schema | Một predicate thường không cần same-element grouping |
| Mảng chứa tất cả các giá trị đã cho | `$all` | Yêu cầu các giá trị cùng tồn tại, không bắt cùng một phần tử |
| Hai loại item riêng cùng tồn tại | Nhiều `$elemMatch` qua `$all` / `$and` | Hai nhóm điều kiện có thể thuộc item khác nhau |
| Trả **một** phần tử khớp đầu tiên | Projection `$elemMatch` | Giới hạn phần tử hiển thị |
| Trả **tất cả** phần tử khớp | Aggregation `$filter` | Duyệt/filter từng phần tử |
| Thống kê mỗi item hoặc group theo item | `$unwind`, `$match`, `$group` | Biến item thành đầu vào pipeline |
| Cập nhật những item thỏa điều kiện | `$[identifier]` và `arrayFilters` | Chọn phần tử để sửa |
| So sánh vị trí hoặc cặp phần tử phức tạp | Aggregation hoặc thiết kế lại data model | Cần logic vượt quá một phép kiểm tra tồn tại |
| Mảng cực lớn có truy vấn độc lập theo item | Collection con với index | Giới hạn document, chi phí cập nhật và truy cập |

## 17. Các sai lầm phổ biến

### Sai lầm 1 — Giả định hai dotted predicate cùng item

~~~javascript
{
  "items.sku": "A",
  "items.qty": { $gte: 3 }
}
~~~

Truy vấn này có thể lấy `ord-1`, `ord-3` sai với yêu cầu “A qty ≥ 3”. Sửa bằng `items: {$elemMatch: {sku:"A", qty:{$gte:3}}}`.

### Sai lầm 2 — Dùng `$and` nhưng vẫn nằm ngoài `$elemMatch`

~~~javascript
{
  $and: [
    { "items.sku": "A" },
    { "items.qty": { $gte: 3 } }
  ]
}
~~~

`$and` không gắn hai điều kiện vào cùng item.

### Sai lầm 3 — Dùng hai `$elemMatch` riêng khi muốn một phần tử

~~~javascript
{
  $and: [
    { items: { $elemMatch: { sku: "A" } } },
    { items: { $elemMatch: { qty: { $gte: 3 } } } }
  ]
}
~~~

Điều này có thể khớp A và qty từ **hai item khác nhau**. Khi yêu cầu cùng item, gộp hai predicate **vào một `$elemMatch`**.

### Sai lầm 4 — Tưởng `$elemMatch` filter cắt mảng trả về

Truy vấn với `$elemMatch` chỉ chọn document; muốn giữ phần tử trả về cần projection hoặc aggregation.

### Sai lầm 5 — Dùng projection `$elemMatch` để lấy toàn bộ item thỏa

Projection `$elemMatch` trả **phần tử đầu tiên**. Nếu muốn mọi item, dùng `$filter`.

### Sai lầm 6 — Coi mảng rỗng là có phần tử thỏa

Không có item nào thì `$elemMatch` không khớp. Đặc biệt, câu “mọi item đều hợp lệ” cần quy định rõ có chấp nhận mảng rỗng hay không.

### Sai lầm 7 — Coi các toán tử phủ định như toán tử khẳng định

`"items.sku": {$ne:"A"}` có thể có nghĩa không chứa A, còn `items:{$elemMatch:{sku:{$ne:"A"}}}` có nghĩa tồn tại item không phải A. Hãy viết điều kiện theo đúng ý định.

### Sai lầm 8 — Đặt query predicate đúng nhưng index sai

Index đơn trên `items.sku` có thể không đủ tối ưu query có cả `qty`, còn compound index lại tăng chi phí ghi. Đo bằng `explain` trên data thực thay vì suy luận từ số index.

### Sai lầm 9 — Chỉ dựa vào kết quả với một document mẫu

Nếu mọi đơn chỉ có một item, dotted predicate và `$elemMatch` có thể cho cùng kết quả, che giấu lỗi. Test bắt buộc nên có **hai item mỗi cái thỏa một nửa điều kiện**.

### Sai lầm 10 — Quên schema hỗn hợp

Document chứa `items` là object đơn có thể khớp dot notation nhưng không khớp `$elemMatch`. Cần schema validation, migration hoặc xử lý legacy data rõ ràng.

## 18. Bài thực hành: viết truy vấn và dự đoán kết quả

Sử dụng `db.orders` đã tạo ở đầu bài. Trước mỗi lệnh, hãy **dự đoán những ID nào được trả về**, sau đó chạy trong mongosh để quan sát.

### Bài 1 — Điều kiện same-element cơ bản

Tìm đơn có item `sku = "A"` và `qty >= 3`. Viết hai query: một dùng dot notation, một dùng `$elemMatch`. Giải thích vì sao khác kết quả.

**Gợi ý:** `ord-1` có A:1 và B:5; đây là ca kiểm thử phân biệt hai cách viết.

### Bài 2 — Ba điều kiện cùng item

Tìm đơn có item B, qty ≥ 4, warehouse HCM. Không được ghép SKU từ một item với warehouse của item khác. Trả `_id` của đơn.

### Bài 3 — Điều kiện khoảng trên array scalar

Tìm đơn có **một** giá trị `scores` trong khoảng `[80, 90)`. So sánh kết quả với query không dùng `$elemMatch`.

### Bài 4 — Cùng object lồng nhau

Tìm đơn có item A, qty ≥ 3, `options.color = "red"` và `options.size = "M"`.

### Bài 5 — Mảng lồng nhau

Tìm đơn có item A qty ≥ 3 và promotion VIP active **của chính item A**.

### Bài 6 — Hai nhóm phần tử

Tìm đơn có item A qty ≥ 2 **và** item B qty ≥ 4. Giải thích vì sao cần hai nhóm điều kiện tồn tại riêng.

### Bài 7 — Phủ định

Viết query cho hai yêu cầu:

1. Không chứa item nào có `sku = "A"`.
2. Có ít nhất một item với `sku != "A"`.

Đối chiếu trên `ord-1` và giải thích khác biệt.

### Bài 8 — Projection

Truy vấn `ord-5` và chỉ trả item đầu tiên có qty ≥ 3 bằng projection. Sau đó dùng `$filter` để trả **tất cả** item có qty ≥ 3.

### Bài 9 — Truy vấn và index

Tạo index `{"items.sku":1, "items.qty":1}`, so sánh `explain("executionStats")` cho query có `$elemMatch` và query bằng dot notation. Không cần kết luận index thắng trên bộ dữ liệu rất nhỏ; hãy chỉ ra `winningPlan` và số key/document được kiểm tra.

### Bài 10 — Thiết kế API

Giả sử API:

~~~http
GET /orders?sku=A&minQty=3&warehouse=HCM
~~~

Hãy viết câu query MongoDB đúng và một bộ test gồm:

- Có A:1 và B:5 tại HCM.
- Có A:3 tại HCM.
- Có A:3 tại HN và B:5 tại HCM.
- Có A:3 tại HCM nhưng item cũng chứa object option không liên quan.
- `items` rỗng hoặc thiếu field.

Giải thích trường hợp nào phải được trả về và vì sao.

## 19. Đáp án định hướng cho bộ dữ liệu mẫu

### Bài 1

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 }
    }
  }
}, { _id: 1 })
~~~

Kết quả same-element: `ord-2`, `ord-5`. Dot notation riêng có thể trả thêm `ord-1`, `ord-3` và `ord-6`.

### Bài 2

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "B",
      qty: { $gte: 4 },
      warehouse: "HCM"
    }
  }
}, { _id: 1 })
~~~

Kết quả: `ord-3`, `ord-5`. `ord-1` có B:5 nhưng ở HN.

### Bài 3

~~~javascript
db.orders.find({
  scores: {
    $elemMatch: {
      $gte: 80,
      $lt: 90
    }
  }
}, { _id: 1 })
~~~

Kết quả: `ord-2`, `ord-3`. Không dùng `$elemMatch` có thể lấy thêm `ord-1`.

### Bài 4

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      "options.color": "red",
      "options.size": "M"
    }
  }
}, { _id: 1 })
~~~

Kết quả: `ord-2`.

### Bài 5

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      promotions: {
        $elemMatch: {
          code: "VIP",
          active: true
        }
      }
    }
  }
}, { _id: 1 })
~~~

Kết quả: `ord-2`.

### Bài 6

~~~javascript
db.orders.find({
  items: {
    $all: [
      { $elemMatch: { sku: "A", qty: { $gte: 2 } } },
      { $elemMatch: { sku: "B", qty: { $gte: 4 } } }
    ]
  }
}, { _id: 1 })
~~~

Kết quả: `ord-3`, `ord-5`.

### Bài 7

~~~javascript
// Không có item A.
db.orders.find({
  $nor: [
    { items: { $elemMatch: { sku: "A" } } }
  ]
})

// Tồn tại item có sku khác A.
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $ne: "A" }
    }
  }
})
~~~

`ord-1` không thỏa truy vấn thứ nhất nhưng thỏa truy vấn thứ hai. Truy vấn thứ nhất có thể bao gồm document thiếu mảng hoặc có object đơn, do không tìm thấy phần tử mảng mang SKU A; nếu chỉ cho phép array hợp lệ, thêm ràng buộc kiểu/schema.

### Bài 8

~~~javascript
db.orders.find(
  { _id: "ord-5" },
  {
    items: {
      $elemMatch: {
        qty: { $gte: 3 }
      }
    }
  }
)
~~~

Projection `$elemMatch` chỉ cho phần tử B:7 (đầu tiên trong mảng). Aggregation `$filter` với `qty >= 3` cho cả B:7 và A:3.

### Bài 9

Không có một số liệu `IXSCAN`/`COLLSCAN` bắt buộc trên bộ data demo. Kết quả phụ thuộc query planner và môi trường; cần so `totalKeysExamined`, `totalDocsExamined`, `nReturned`, bộ index và mức tải thực tế.

### Bài 10

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 3 },
      warehouse: "HCM"
    }
  }
})
~~~

Chỉ đơn có **một item A qty ≥ 3 tại HCM** được trả về. Việc document khác có B:5 tại HCM không làm A:1 hoặc A:3 tại HN thành hợp lệ.

## 20. Tóm tắt cú pháp để tra cứu nhanh

| Nhu cầu | Mẫu truy vấn / pipeline |
|---|---|
| Một item có A và qty ≥ 3 | `{items: {$elemMatch: {sku:"A", qty:{$gte:3}}}}` |
| Một score trong [80, 90) | `{scores: {$elemMatch: {$gte:80, $lt:90}}}` |
| Cùng item có màu đỏ | `{items: {$elemMatch: {sku:"A", "options.color":"red"}}}` |
| Item A có promotion VIP active | `{items: {$elemMatch: {sku:"A", promotions:{$elemMatch:{code:"VIP",active:true}}}}}` |
| Có một item A và một item B theo điều kiện riêng | `{items: {$all: [{$elemMatch:{sku:"A"}}, {$elemMatch:{sku:"B"}}]}}` |
| Chọn document nhưng giữ nguyên mảng khi trả về | `find({items: {$elemMatch: {...}}})` |
| Chỉ lấy phần tử khớp đầu tiên | `find(filter, {items: {$elemMatch: {...}}})` |
| Lấy mọi phần tử khớp | Aggregation `$project` + `$filter` |
| Tách từng phần tử để phân tích | Aggregation `$unwind` rồi `$match` |
| Cập nhật phần tử khớp | Positional `$` hoặc `$[identifier]` với `arrayFilters` |
| Tối ưu tìm item theo SKU/qty | Compound multikey index thích hợp + đo `explain` |

Điều cần ghi nhớ là: **một điều kiện trên một field mảng có thể đúng vì phần tử này, điều kiện khác có thể đúng vì phần tử kia**. Khi ý nghĩa nghiệp vụ đòi hỏi mọi predicate cùng đúng trên **một phần tử**, đặt chúng bên trong **một `$elemMatch`**. Việc đặt đúng toán tử vừa bảo vệ kết quả truy vấn, vừa giúp MongoDB có cơ hội tận dụng multikey index phù hợp. Sau đó, chọn projection, aggregation hoặc arrayFilters theo mục tiêu **trả phần tử**, **thống kê phần tử** hay **cập nhật phần tử**; đừng đồng nhất những nhiệm vụ đó với việc lọc document.
