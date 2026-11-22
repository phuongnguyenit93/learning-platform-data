# Kết hợp điều kiện bằng $and, $or, $nor và $not trong MongoDB

Trong MongoDB, một truy vấn tài liệu thường phải kiểm tra **nhiều điều kiện đồng thời**: tìm sản phẩm đang bán **và** còn hàng; lấy đơn thuộc một trong hai trạng thái; loại bỏ nhóm dữ liệu không được phép hiển thị; hoặc phủ định một phép so sánh cụ thể. Bốn toán tử truy vấn logic **`$and`**, **`$or`**, **`$nor`** và **`$not`** cho phép diễn đạt các quy tắc đó trực tiếp trong filter của `find()`, `countDocuments()`, `updateMany()` và stage `$match` của aggregation.

Bài học hướng dẫn cách đọc biểu thức logic, viết đúng cú pháp, lồng các toán tử, xử lý trường vắng mặt, tránh lỗi khi ghép filter bằng JavaScript, đồng thời xem xét tác động tới index và hiệu năng.

## 1. Tư duy logic trước khi viết truy vấn

Giả sử:

- **A**: sản phẩm có `category = "laptop"`.
- **B**: sản phẩm có `stock > 0`.

Ta muốn diễn đạt các quy tắc khác nhau:

| Quy tắc | Diễn giải | Toán tử MongoDB |
| --- | --- | --- |
| A **và** B | Chỉ lấy laptop còn hàng | `$and` hoặc các điều kiện ngầm định AND |
| A **hoặc** B | Lấy laptop, hoặc bất kỳ sản phẩm nào còn hàng | `$or` |
| **Không** (A hoặc B) | Loại mọi laptop và mọi sản phẩm còn hàng | `$nor` |
| **Không** B | Lấy tài liệu không thỏa điều kiện `stock > 0` | `$not` đặt trên trường `stock`; có lưu ý về trường thiếu |

Bảng chân trị hai biến, với **1** là đúng và **0** là sai:

| A | B | A AND B | A OR B | NOR(A, B) | NOT A |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 1 | 1 |
| 0 | 1 | 0 | 1 | 0 | 1 |
| 1 | 0 | 0 | 1 | 0 | 0 |
| 1 | 1 | 1 | 1 | 0 | 0 |

Điểm quan trọng về cú pháp MongoDB:

- **`$and`, `$or`, `$nor`** nhận **một mảng các biểu thức filter**. Mỗi phần tử có thể chứa một hoặc nhiều điều kiện.
- **`$not`** là **toán tử ở cấp trường**, đặt bên trong điều kiện của một field và phủ định biểu thức toán tử áp dụng lên field đó. Nó không phải toán tử phủ định toàn bộ filter ở cấp gốc.
- MongoDB **tự AND** những điều kiện khác khóa nằm trong cùng một object truy vấn. Vì thế nhiều bài toán không cần viết `$and` tường minh.
- Logic của truy vấn là logic khớp tài liệu theo MongoDB; đặc biệt, **field không tồn tại** có thể khiến một số điều kiện phủ định được xem là khớp. Không được giả định các trường đều hiện diện.

## 2. Tạo bộ dữ liệu nhất quán để thực hành

Mở `mongosh` rồi chạy khối lệnh sau trong một database riêng:

~~~javascript
var logicDb = db.getSiblingDB("mongo_query_logic_lab");

logicDb.products.drop();
logicDb.products.insertMany([
  {
    _id: "p01",
    name: "Laptop Alpha",
    category: "laptop",
    price: 1500,
    stock: 5,
    status: "active",
    brand: "ACME",
    rating: 4.7,
    tags: ["tech", "featured"]
  },
  {
    _id: "p02",
    name: "Laptop Beta",
    category: "laptop",
    price: 900,
    stock: 0,
    status: "active",
    brand: "Zen",
    rating: 4.3,
    tags: ["tech"]
  },
  {
    _id: "p03",
    name: "Phone Alpha",
    category: "phone",
    price: 700,
    stock: 12,
    status: "active",
    brand: "ACME",
    rating: 4.6,
    tags: ["tech", "sale"]
  },
  {
    _id: "p04",
    name: "Phone Beta",
    category: "phone",
    price: 1200,
    stock: 2,
    status: "draft",
    brand: "Zen",
    rating: 4.8,
    tags: ["premium"]
  },
  {
    _id: "p05",
    name: "MongoDB Handbook",
    category: "book",
    price: 40,
    stock: 30,
    status: "active",
    brand: "Books",
    rating: 4.9,
    tags: ["education"]
  },
  {
    _id: "p06",
    name: "Laptop Pro",
    category: "laptop",
    price: 2200,
    stock: 1,
    status: "archived",
    brand: "ACME",
    rating: 4.5,
    tags: ["premium"]
  },
  {
    _id: "p07",
    name: "USB Cable",
    category: "accessory",
    price: 120,
    stock: 0,
    status: "active",
    brand: "Value",
    rating: 3.8,
    tags: ["sale"]
  },
  {
    _id: "p08",
    name: "Budget Phone",
    category: "phone",
    price: 500,
    stock: 7,
    status: "active",
    // Cố ý không khai báo brand và rating.
    tags: ["budget"]
  },
  {
    _id: "p09",
    name: "Phone Case",
    category: "accessory",
    price: 90,
    stock: 15,
    // Cố ý không khai báo status.
    brand: "Zen",
    rating: 4.0,
    tags: ["sale"]
  }
]);
~~~

Hai loại trường thiếu ở `p08` và `p09` giúp kiểm tra hành vi phủ định trong MongoDB. Tất cả tài liệu vẫn có `_id`, `category`, `price` và `stock`.

Để đọc nhanh danh sách `_id` khớp một filter, định nghĩa một hàm dùng cho các ví dụ:

~~~javascript
function ids(filter) {
  return logicDb.products
    .find(filter, { _id: 1 })
    .sort({ _id: 1 })
    .toArray()
    .map(document => document._id);
}

ids({}); // p01 đến p09
~~~

Nếu muốn quan sát toàn bộ tài liệu thay vì chỉ `_id`, hãy dùng `logicDb.products.find(filter)` trực tiếp. Phần kết quả liệt kê trong bài áp dụng cho **dữ liệu ban đầu**, trước khi có bất kỳ thao tác cập nhật nào.

## 3. Toán tử $and: tất cả điều kiện đều phải đúng

### 3.1. Cú pháp và cách đọc

Cú pháp:

~~~javascript
{
  $and: [
    { conditionA },
    { conditionB },
    { conditionC }
  ]
}
~~~

Mỗi biểu thức trong mảng phải khớp thì tài liệu mới được trả về. Ví dụ “laptop có giá từ 1.000 trở lên **và** còn hàng”:

~~~javascript
ids({
  $and: [
    { category: "laptop" },
    { price: { $gte: 1000 } },
    { stock: { $gt: 0 } }
  ]
});
// ["p01", "p06"]
~~~

`p02` là laptop nhưng giá 900 và hết hàng. `p01` và `p06` đều thỏa ba điều kiện, dù `p06` có trạng thái `archived`; truy vấn **không yêu cầu** trạng thái nào, nên `p06` vẫn được trả về.

Nếu chỉ lấy laptop còn bán:

~~~javascript
ids({
  $and: [
    { category: "laptop" },
    { price: { $gte: 1000 } },
    { stock: { $gt: 0 } },
    { status: "active" }
  ]
});
// ["p01"]
~~~

### 3.2. AND ngầm định trong một object

MongoDB dùng **AND ngầm định** cho các trường khác nhau xuất hiện cùng cấp trong filter. Truy vấn ở trên có thể viết ngắn hơn:

~~~javascript
ids({
  category: "laptop",
  price: { $gte: 1000 },
  stock: { $gt: 0 },
  status: "active"
});
// ["p01"]
~~~

Hai cách biểu đạt cùng quy tắc. Khi các điều kiện đơn giản và tác động đến những field khác nhau, AND ngầm định thường dễ đọc.

### 3.3. Nhiều điều kiện trên cùng một trường

Muốn lấy sản phẩm có giá từ 700 đến 1.500, hai cận cần cùng đúng:

~~~javascript
ids({
  price: { $gte: 700, $lte: 1500 }
});
// ["p01", "p02", "p03", "p04"]
~~~

Có thể diễn đạt bằng `$and` tường minh:

~~~javascript
ids({
  $and: [
    { price: { $gte: 700 } },
    { price: { $lte: 1500 } }
  ]
});
// ["p01", "p02", "p03", "p04"]
~~~

Cách đầu gọn hơn với các toán tử khác nhau trên cùng field. `$and` hữu ích khi cần kết hợp những nhánh truy vấn phức tạp hoặc tránh trùng khóa object.

### 3.4. Không được lặp khóa trong JavaScript object

Ví dụ dưới đây **không diễn đạt hai điều kiện cùng lúc**:

~~~javascript
// SAI về ý định: JavaScript chỉ giữ giá trị của khóa price cuối cùng.
var wrongFilter = {
  price: { $gte: 700 },
  price: { $lte: 1500 }
};
~~~

Với một object JavaScript thông thường, khóa `price` bị lặp; biểu thức sau ghi đè biểu thức trước. Vì vậy chỉ còn điều kiện `$lte: 1500`.

Cách đúng:

~~~javascript
// Gộp hai toán tử của cùng field.
var correctFilter = {
  price: { $gte: 700, $lte: 1500 }
};

// Hoặc dùng mảng $and.
var anotherCorrectFilter = {
  $and: [
    { price: { $gte: 700 } },
    { price: { $lte: 1500 } }
  ]
};
~~~

Lỗi tương tự có thể xảy ra khi ghép hai object có cùng khóa `$or` hoặc `$and` bằng cách spread: điều kiện cuối có thể thay thế điều kiện trước. Phần về điều kiện lồng nhau sẽ cho ví dụ khắc phục.

## 4. Toán tử $or: ít nhất một nhánh đúng

### 4.1. Cú pháp

~~~javascript
{
  $or: [
    { conditionA },
    { conditionB },
    { conditionC }
  ]
}
~~~

MongoDB trả về tài liệu nếu **ít nhất một** biểu thức trong mảng khớp. `$or` là OR bao hàm: trường hợp thỏa **cả hai nhánh** cũng được chấp nhận.

Ví dụ “điện thoại **hoặc** sản phẩm hết hàng”:

~~~javascript
ids({
  $or: [
    { category: "phone" },
    { stock: 0 }
  ]
});
// ["p02", "p03", "p04", "p07", "p08"]
~~~

Diễn giải:

- `p03`, `p04`, `p08` là điện thoại.
- `p02` và `p07` không phải điện thoại, nhưng có `stock: 0`.
- Nếu một tài liệu vừa là điện thoại vừa hết hàng, nó vẫn chỉ xuất hiện **một lần** trong kết quả của `find()`.

### 4.2. Kết hợp một điều kiện cố định với $or

Bài toán: “sản phẩm **active** và thuộc **laptop hoặc phone**”. Viết:

~~~javascript
ids({
  status: "active",
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});
// ["p01", "p02", "p03", "p08"]
~~~

Điều kiện `status: "active"` kết hợp bằng AND ngầm định với kết quả toàn bộ `$or`. Có thể đọc:

~~~text
status = active
AND
(category = laptop OR category = phone)
~~~

`p04` là phone nhưng `draft`; `p06` là laptop nhưng `archived`. Cả hai không khớp. `p09` thiếu `status` nên cũng không khớp.

### 4.3. Khi OR cùng kiểm tra một field: cân nhắc $in

Nếu nhiều nhánh chỉ so sánh **cùng trường bằng các giá trị khác nhau**, `$in` thường gọn hơn:

~~~javascript
// Viết bằng $or.
ids({
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});

// Viết bằng $in, tương đương trong ví dụ này.
ids({
  category: { $in: ["laptop", "phone"] }
});
// ["p01", "p02", "p03", "p04", "p06", "p08"]
~~~

Dùng `$or` khi các nhánh chứa điều kiện khác trường hoặc mỗi nhánh có cấu trúc riêng. Ví dụ “điện thoại giá dưới 600 **hoặc** laptop giá trên 2.000”:

~~~javascript
ids({
  $or: [
    { category: "phone", price: { $lt: 600 } },
    { category: "laptop", price: { $gt: 2000 } }
  ]
});
// ["p06", "p08"]
~~~

Mỗi phần tử của mảng `$or` là một **object điều kiện hoàn chỉnh**. Trong nhánh thứ nhất, `category: "phone"` và `price: { $lt: 600 }` được nối bằng AND ngầm định.

### 4.4. OR không bảo đảm thứ tự kết quả

Các toán tử logic quyết định **tài liệu nào khớp**, không quyết định thứ tự trả về. Khi cần thứ tự ổn định cho phân trang hoặc kiểm thử, dùng `sort()`:

~~~javascript
logicDb.products
  .find({
    $or: [
      { category: "laptop" },
      { category: "phone" }
    ]
  })
  .sort({ price: 1, _id: 1 })
  .toArray();
~~~

Trong đó `price: 1` là tăng dần và `_id: 1` làm tiêu chí phụ khi hai sản phẩm có cùng giá.

## 5. Toán tử $nor: không nhánh nào được đúng

### 5.1. Cú pháp và ý nghĩa phủ định OR

Cú pháp:

~~~javascript
{
  $nor: [
    { conditionA },
    { conditionB }
  ]
}
~~~

Toán tử `$nor` khớp khi **mọi biểu thức con đều không khớp**, tương ứng:

~~~text
NOR(A, B) = NOT (A OR B)
          = (NOT A) AND (NOT B)
~~~

Ví dụ “không phải điện thoại **và** cũng không phải hàng hết kho”:

~~~javascript
ids({
  $nor: [
    { category: "phone" },
    { stock: 0 }
  ]
});
// ["p01", "p05", "p06", "p09"]
~~~

`p02`, `p07` bị loại vì hết hàng; `p03`, `p04`, `p08` bị loại vì là phone. Những tài liệu còn lại thỏa cả hai điều kiện phủ định.

### 5.2. Một nhánh $nor có thể chứa nhiều điều kiện AND

Bài toán: “loại những sản phẩm **vừa active vừa có giá ít nhất 1.000**”, nhưng giữ những sản phẩm khác.

~~~javascript
ids({
  $nor: [
    {
      status: "active",
      price: { $gte: 1000 }
    }
  ]
});
// ["p02", "p03", "p04", "p05", "p06", "p07", "p08", "p09"]
~~~

Duy nhất `p01` bị loại, vì `p01` thỏa **cả hai** điều kiện trong cùng một nhánh.

**Đừng nhầm** với truy vấn sau:

~~~javascript
ids({
  $nor: [
    { status: "active" },
    { price: { $gte: 1000 } }
  ]
});
~~~

Truy vấn thứ hai loại **mọi sản phẩm active** **hoặc** **mọi sản phẩm giá từ 1.000 trở lên**; phạm vi loại trừ rộng hơn nhiều. Vị trí đặt các điều kiện bên trong hay bên ngoài từng phần tử mảng `$nor` quyết định ý nghĩa.

### 5.3. $nor và field không tồn tại

Thông thường, một điều kiện ví dụ `{ rating: { $gte: 4.5 } }` **không khớp** tài liệu thiếu `rating`. Khi dùng `$nor` để phủ định, tài liệu thiếu field có thể được giữ lại:

~~~javascript
ids({
  $nor: [
    { rating: { $gte: 4.5 } }
  ]
});
// ["p02", "p07", "p08", "p09"]
~~~

`p08` thiếu `rating` nhưng vẫn được lấy. Nếu yêu cầu “**đã có điểm** và điểm **dưới 4,5**”, phải yêu cầu field tồn tại hoặc dùng trực tiếp phép so sánh phù hợp:

~~~javascript
ids({
  rating: { $lt: 4.5 }
});
// ["p02", "p07", "p09"]
~~~

Ở đây `$lt` với giá trị số không tự khớp field bị thiếu. Khi muốn phủ định một điều kiện phức tạp nhưng chỉ áp dụng cho document có field, có thể ghép `$exists: true` với biểu thức phủ định.

**Ngoại lệ cần hiểu:** Nếu phần tử trong `$nor` chính là `{ rating: { $exists: false } }`, thì kết quả `$nor` chỉ bao gồm các tài liệu **có trường rating**, vì nó phủ định điều kiện “trường không tồn tại”:

~~~javascript
ids({
  $nor: [
    { rating: { $exists: false } }
  ]
});
// ["p01", "p02", "p03", "p04", "p05", "p06", "p07", "p09"]
~~~

Vì thế không nên ghi nhớ máy móc rằng “`$nor` luôn bao gồm tài liệu thiếu field”. Kết quả phụ thuộc vào **điều kiện con thực sự đang bị phủ định**.

## 6. Toán tử $not: phủ định một điều kiện trên field

### 6.1. $not được đặt ở đâu?

Toán tử `$not` có dạng:

~~~javascript
{
  fieldName: {
    $not: {
      $someOperator: someValue
    }
  }
}
~~~

Hoặc với regular expression, có thể dùng `$not` trực tiếp với regex. `$not` áp dụng cho **điều kiện của một trường**, khác với `$nor` là toán tử cấp filter nhận các nhánh biểu thức.

Ví dụ tìm sản phẩm **không có giá lớn hơn 1.000**:

~~~javascript
ids({
  price: {
    $not: { $gt: 1000 }
  }
});
// ["p02", "p03", "p05", "p07", "p08", "p09"]
~~~

Tất cả sản phẩm đều có `price`, nên tập kết quả giống điều kiện `price <= 1000` trong bộ dữ liệu hiện tại. Tuy nhiên hai cách **không tương đương hoàn toàn khi trường bị thiếu hoặc kiểu dữ liệu khác**, vì `$not` còn khớp tài liệu không có field.

### 6.2. $not với $gte và trường thiếu

Tìm các sản phẩm **không có rating từ 4,5 trở lên**:

~~~javascript
ids({
  rating: {
    $not: { $gte: 4.5 }
  }
});
// ["p02", "p07", "p08", "p09"]
~~~

`p08` được trả về vì **không có trường rating**. Nếu chỉ muốn sản phẩm **có rating** nhưng không đạt 4,5:

~~~javascript
ids({
  $and: [
    { rating: { $exists: true } },
    { rating: { $not: { $gte: 4.5 } } }
  ]
});
// ["p02", "p07", "p09"]
~~~

Trường hợp điều kiện đơn giản, viết `rating: { $lt: 4.5 }` sẽ rõ ràng hơn. Ví dụ tách `$exists` ở trên giúp hiểu semantics của phủ định.

### 6.3. $not với biểu thức chính quy

Tìm các sản phẩm có `brand` **không bắt đầu bằng chữ A**:

~~~javascript
ids({
  brand: {
    $not: /^A/
  }
});
// ["p02", "p04", "p05", "p07", "p08", "p09"]
~~~

Hoặc dùng cú pháp `$regex`:

~~~javascript
ids({
  brand: {
    $not: { $regex: "^A" }
  }
});
// ["p02", "p04", "p05", "p07", "p08", "p09"]
~~~

`p01`, `p03`, `p06` có brand `"ACME"` nên bị loại. `p08` **không có brand**, nhưng vẫn khớp điều kiện phủ định. Nếu bài toán yêu cầu “brand đã được khai báo và không bắt đầu bằng A”, thêm `{ brand: { $exists: true } }` vào một mệnh đề `$and`.

### 6.4. $not không thay thế phủ định của cả tài liệu

Ví dụ **không hợp lệ về cách đặt toán tử**:

~~~javascript
// SAI: $not không phải toán tử filter cấp gốc.
{
  $not: {
    status: "active",
    stock: { $gt: 0 }
  }
}
~~~

Muốn phủ định **một biểu thức gồm nhiều trường**, dùng `$nor` với một nhánh:

~~~javascript
// NOT (status = active AND stock > 0)
{
  $nor: [
    {
      status: "active",
      stock: { $gt: 0 }
    }
  ]
}
~~~

Nếu muốn phủ định **mỗi điều kiện riêng** rồi kết hợp, cần diễn đạt đúng công thức logic. Không thể tùy ý chuyển một `$not` cấp field thành `$nor` nhiều nhánh mà không kiểm tra ý nghĩa.

### 6.5. So sánh $not, $ne và $nin

MongoDB cung cấp các toán tử chuyên biệt cho những trường hợp phủ định đơn giản:

~~~javascript
// Giá trị status không bằng active.
ids({ status: { $ne: "active" } });
// ["p04", "p06", "p09"]

// Status không thuộc hai giá trị active hoặc draft.
ids({ status: { $nin: ["active", "draft"] } });
// ["p06", "p09"]

// Một cách diễn đạt phủ định phép bằng trên status.
ids({ status: { $not: { $eq: "active" } } });
// ["p04", "p06", "p09"]
~~~

Trong các ví dụ này, `p09` thiếu `status`, nhưng vẫn khớp các toán tử phủ định. Nếu muốn giới hạn trường hợp **có trạng thái**, thêm `status: { $exists: true }` một cách rõ ràng vào cấu trúc truy vấn.

**Quy tắc thực dụng:** dùng `$ne` cho “khác một giá trị”, `$nin` cho “không thuộc danh sách”, `$not` khi muốn phủ định một toán tử của field (đặc biệt regex), và `$nor` khi muốn phủ định một hoặc nhiều nhánh filter.

## 7. Lồng các toán tử để biểu diễn nghiệp vụ

Phần lớn truy vấn thực tế không dừng ở một toán tử. Cần bắt đầu từ **ngoặc logic bằng lời**, sau đó chuyển thành biểu thức MongoDB.

### 7.1. A AND (B OR C)

Yêu cầu: chỉ lấy sản phẩm **active**, có **stock > 0**, thuộc **laptop hoặc phone**.

~~~text
(status = active)
AND (stock > 0)
AND (category = laptop OR category = phone)
~~~

MongoDB:

~~~javascript
ids({
  status: "active",
  stock: { $gt: 0 },
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});
// ["p01", "p03", "p08"]
~~~

`p02` là laptop active nhưng hết hàng; `p04` là phone còn hàng nhưng draft; `p06` là laptop còn hàng nhưng archived.

Đối với hai giá trị của cùng trường `category`, cũng có thể viết gọn:

~~~javascript
ids({
  status: "active",
  stock: { $gt: 0 },
  category: { $in: ["laptop", "phone"] }
});
// ["p01", "p03", "p08"]
~~~

### 7.2. (A OR B) AND (C OR D)

Yêu cầu: sản phẩm thuộc nhóm laptop hoặc phone, **đồng thời** có brand ACME hoặc còn hơn 5 đơn vị tồn kho.

~~~text
(category = laptop OR category = phone)
AND
(brand = ACME OR stock > 5)
~~~

MongoDB:

~~~javascript
ids({
  $and: [
    {
      $or: [
        { category: "laptop" },
        { category: "phone" }
      ]
    },
    {
      $or: [
        { brand: "ACME" },
        { stock: { $gt: 5 } }
      ]
    }
  ]
});
// ["p01", "p03", "p06", "p08"]
~~~

Phải dùng `$and` chứa **hai `$or` riêng**. Đoạn sau gây lỗi logic trong JavaScript vì hai khóa `$or` trùng nhau:

~~~javascript
// SAI: phần $or thứ hai ghi đè phần đầu.
var wrongNestedFilter = {
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ],
  $or: [
    { brand: "ACME" },
    { stock: { $gt: 5 } }
  ]
};
~~~

Không chạy điều kiện này trong sản phẩm nếu chưa nhận biết lỗi: filter cuối cùng chỉ còn nhánh về brand/stock và có thể làm lọt tài liệu ngoài nhóm category mong muốn.

### 7.3. NOT (A OR B)

Yêu cầu: sản phẩm không phải phone **và** không hết hàng.

~~~javascript
ids({
  $nor: [
    { category: "phone" },
    { stock: 0 }
  ]
});
// ["p01", "p05", "p06", "p09"]
~~~

`$nor` là cách diễn đạt trực tiếp của `NOT (A OR B)`. Khi một field có thể vắng mặt, hãy quyết định rõ có giữ tài liệu đó trong kết quả hay không.

### 7.4. NOT (A AND B)

Yêu cầu: loại sản phẩm **active đồng thời giá cao hơn hoặc bằng 1.000**.

~~~javascript
ids({
  $nor: [
    {
      status: "active",
      price: { $gte: 1000 }
    }
  ]
});
// ["p02", "p03", "p04", "p05", "p06", "p07", "p08", "p09"]
~~~

Phủ định của **A AND B** tương đương **NOT A OR NOT B** theo định luật De Morgan. Viết một mệnh đề `$nor` với một nhánh AND ngầm định thường rõ ý hơn trong ví dụ này.

### 7.5. Điều kiện loại trừ ở bên trong $or

Yêu cầu: chọn laptop **active** nhưng giá không quá 1.000, hoặc phone **active** có tồn kho ít nhất 10.

~~~javascript
ids({
  $or: [
    {
      category: "laptop",
      status: "active",
      price: { $lte: 1000 }
    },
    {
      category: "phone",
      status: "active",
      stock: { $gte: 10 }
    }
  ]
});
// ["p02", "p03"]
~~~

Mỗi nhánh là một tập điều kiện nối bằng AND ngầm định; toàn bộ mảng là OR. Bản thân điều kiện giá/tồn kho chỉ áp dụng cho **đúng nhánh** tương ứng.

Nếu chuyển `price` và `stock` ra ngoài `$or` mà không xem xét logic, truy vấn sẽ đổi nghĩa: lúc đó có thể buộc **cả laptop lẫn phone** thỏa cùng điều kiện.

## 8. $and, $or, $nor, $not khi làm việc với mảng

MongoDB có thể so sánh field kiểu mảng theo **phần tử** trong nhiều toán tử query. Bộ dữ liệu ví dụ có `tags` dạng mảng chuỗi:

~~~javascript
// Có ít nhất một phần tử tags bằng "sale".
ids({ tags: "sale" });
// ["p03", "p07", "p09"]
~~~

Khi phủ định, cần xác định mục tiêu là “không có phần tử nào thỏa” hay “có phần tử khác thỏa”. Ví dụ:

~~~javascript
// Không chứa tag "sale".
ids({
  tags: { $ne: "sale" }
});
// ["p01", "p02", "p04", "p05", "p06", "p08"]

// Phủ định điều kiện chứa tag "sale" bằng $nor.
ids({
  $nor: [
    { tags: "sale" }
  ]
});
// ["p01", "p02", "p04", "p05", "p06", "p08"]
~~~

Hai truy vấn trên cùng kết quả với bộ dữ liệu hiện tại. Nếu sau này có document **không có `tags`**, điều kiện phủ định cũng có thể khớp tài liệu đó. Muốn giới hạn vào tài liệu có mảng `tags`, cần kiểm tra sự tồn tại và kiểu dữ liệu.

Với **mảng object**, trường hợp cần nhiều điều kiện **trên cùng một phần tử** phải dùng `$elemMatch`. Ví dụ document có:

~~~javascript
{
  _id: "example",
  variants: [
    { color: "red", stock: 0 },
    { color: "blue", stock: 5 }
  ]
}
~~~

Điều kiện sau có thể khớp dù hai phần lọc xuất hiện ở **hai phần tử khác nhau**:

~~~javascript
{
  "variants.color": "red",
  "variants.stock": { $gt: 0 }
}
~~~

Muốn bắt buộc một variant **vừa đỏ vừa còn hàng**:

~~~javascript
{
  variants: {
    $elemMatch: {
      color: "red",
      stock: { $gt: 0 }
    }
  }
}
~~~

Muốn tìm document **không có variant đỏ còn hàng**, có thể phủ định biểu thức `$elemMatch` bằng `$nor`:

~~~javascript
{
  $nor: [
    {
      variants: {
        $elemMatch: {
          color: "red",
          stock: { $gt: 0 }
        }
      }
    }
  ]
}
~~~

Ví dụ này là filter minh họa cho một collection có trường `variants`; nó **không phải** một truy vấn trên bộ dữ liệu `products` ở mục 2. Các document thiếu `variants` cũng có thể được trả về bởi phủ định trên; thêm ràng buộc nếu nghiệp vụ không chấp nhận field thiếu.

## 9. Áp dụng filter logic trong các thao tác MongoDB

### 9.1. Đếm document

Có thể dùng cùng filter trong `countDocuments()`:

~~~javascript
logicDb.products.countDocuments({
  status: "active",
  $or: [
    { category: "laptop" },
    { category: "phone" }
  ]
});
// 4
~~~

Bốn tài liệu là `p01`, `p02`, `p03` và `p08`.

### 9.2. Dùng trong aggregation $match

Điều kiện logic trong stage `$match` có cú pháp tương tự filter `find()`:

~~~javascript
logicDb.products.aggregate([
  {
    $match: {
      status: "active",
      stock: { $gt: 0 },
      $or: [
        { category: "laptop" },
        { category: "phone" }
      ]
    }
  },
  {
    $group: {
      _id: "$category",
      productCount: { $sum: 1 },
      totalStock: { $sum: "$stock" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Đầu vào `$group` gồm `p01` (laptop, tồn 5), `p03` (phone, tồn 12) và `p08` (phone, tồn 7). Kết quả dự kiến: laptop có **1 sản phẩm / tổng tồn 5**, phone có **2 sản phẩm / tổng tồn 19**.

Trong `$match`, `$and`/`$or`/`$nor`/`$not` hoạt động như toán tử **query language**. Khi cần logic trên **biểu thức tính toán** bên trong aggregation, MongoDB còn có toán tử biểu thức như `$and`, `$or` và `$not` trong ngữ cảnh aggregation expression, thường dùng trong `$expr` hoặc `$project`. Hai ngữ cảnh có cú pháp khác nhau, đặc biệt `$not`:

~~~javascript
// Query operator: $not nằm dưới tên field.
logicDb.products.find({
  stock: { $not: { $gt: 0 } }
});

// Aggregation expression: $not nhận mảng biểu thức,
// và $gt cũng là biểu thức.
logicDb.products.aggregate([
  {
    $project: {
      _id: 1,
      notInStock: {
        $not: [
          { $gt: ["$stock", 0] }
        ]
      }
    }
  }
]);
~~~

**Không chép nguyên cú pháp `$not` query sang biểu thức `$project`**, hoặc ngược lại.

### 9.3. Điều kiện logic trong updateMany()

Đối với thao tác ghi, filter sẽ chọn **những document nào bị cập nhật**. Vì vậy cần đọc kỹ điều kiện trước khi chạy.

Ví dụ muốn đánh dấu sản phẩm đang bán nhưng đã hết hàng:

~~~javascript
var outOfStockFilter = {
  status: "active",
  stock: 0
};

// Xem trước các ID được chọn.
ids(outOfStockFilter);
// ["p02", "p07"]

// Khi đã xác nhận, mới cập nhật:
logicDb.products.updateMany(
  outOfStockFilter,
  { $set: { needsRestock: true } }
);
~~~

Ví dụ này chỉ dùng AND ngầm định. Nếu nghiệp vụ cần nhiều nhóm lựa chọn:

~~~javascript
var reviewFilter = {
  $or: [
    { status: "draft" },
    {
      status: "active",
      stock: { $lte: 0 }
    }
  ]
};

// Dự kiến: p02, p04, p07 trong dữ liệu ban đầu.
ids(reviewFilter);

// Cùng filter có thể dùng với updateMany() sau khi xem kết quả.
~~~

Lưu ý việc chạy các lệnh update sẽ thay đổi dữ liệu; nếu tiếp tục thực hành các ví dụ ở các mục trước, cần hiểu rằng kết quả có thể khác do document đã được sửa.

## 10. Field bị thiếu, null và điều kiện phủ định

Bài toán truy vấn thường gặp ba trạng thái khác nhau:

1. **Field không tồn tại**.
2. **Field tồn tại với giá trị `null`**.
3. **Field tồn tại với giá trị hợp lệ**, ví dụ số hoặc chuỗi.

MongoDB không phải lúc nào cũng xem ba trạng thái trên giống nhau. Ví dụ với `p09`, field `status` không tồn tại:

~~~javascript
// $ne "active" có thể khớp document không có status.
ids({
  status: { $ne: "active" }
});
// ["p04", "p06", "p09"]
~~~

Nếu ý định thực sự là “tài liệu đã có status và status không active”:

~~~javascript
ids({
  $and: [
    { status: { $exists: true } },
    { status: { $ne: "active" } }
  ]
});
// ["p04", "p06"]
~~~

Tương tự, truy vấn phủ định điểm đánh giá:

~~~javascript
// Bao gồm p08 do rating vắng mặt.
ids({ rating: { $not: { $gte: 4.5 } } });

// Không bao gồm p08 vì yêu cầu rating tồn tại.
ids({
  $and: [
    { rating: { $exists: true } },
    { rating: { $not: { $gte: 4.5 } } }
  ]
});
~~~

Còn một điểm quan trọng: trong MongoDB, filter `{ someField: null }` thông thường có thể khớp **cả trường có giá trị null lẫn trường thiếu**. Nếu cần phân biệt chính xác, phải dùng toán tử kiểu dữ liệu và tồn tại cho phù hợp. Đừng cố suy luận kết quả phủ định từ logic boolean thuần mà bỏ qua semantics của field missing và kiểu BSON.

**Nguyên tắc thiết kế:** với dữ liệu kinh doanh, nên quyết định rõ cách xử lý field thiếu từ đầu. Ví dụ một sản phẩm không có rating nên được xem là “dưới 4,5” hay nên bị loại khỏi báo cáo rating? Hai lựa chọn tạo hai filter khác nhau.

## 11. Tối ưu hiệu năng của truy vấn có nhiều điều kiện

Toán tử logic diễn tả điều kiện đúng/sai, còn hiệu năng phụ thuộc vào **index**, phân bố dữ liệu, từng nhánh truy vấn và trình tối ưu MongoDB. Không thể khẳng định rằng chỉ cần viết `$and` hay `$or` là truy vấn sẽ tự nhanh.

### 11.1. AND và compound index

Các filter dạng:

~~~javascript
{
  status: "active",
  category: "laptop",
  price: { $gte: 1000 }
}
~~~

có thể hưởng lợi từ compound index theo các trường được dùng nhiều trong ứng dụng:

~~~javascript
logicDb.products.createIndex({
  status: 1,
  category: 1,
  price: 1
});
~~~

Lựa chọn thứ tự field trong compound index nên dựa trên workload thực tế, tần suất filter, sort và tính chọn lọc. Ví dụ trên có hai điều kiện bằng và một điều kiện khoảng; đây là trường hợp thường được cân nhắc khi thiết kế index.

### 11.2. OR và index cho từng nhánh

Với `$or`, MongoDB có thể dùng các index khác nhau để hỗ trợ các nhánh tương ứng, khi các nhánh đủ điều kiện sử dụng index. Nếu một nhánh không được hỗ trợ hiệu quả bởi index, truy vấn `$or` có thể phải dựa vào collection scan tùy trường hợp.

Ví dụ:

~~~javascript
logicDb.products.createIndex({ category: 1 });
logicDb.products.createIndex({ stock: 1 });

var orFilter = {
  $or: [
    { category: "phone" },
    { stock: 0 }
  ]
};
~~~

Hai index giúp tạo cơ hội tối ưu cho từng nhánh nhưng không đảm bảo mọi truy vấn sẽ dùng cả hai: MongoDB optimizer chọn kế hoạch dựa vào chi phí ước tính, kích thước và phân bố dữ liệu. Với collection chỉ có chín tài liệu, **COLLSCAN có thể hợp lý hơn IXSCAN**.

### 11.3. Phủ định có thể kém chọn lọc

Các điều kiện `$ne`, `$nin`, `$not` hoặc `$nor` thường giữ lại một tập dữ liệu lớn khi đối tượng bị loại trừ chiếm tỷ lệ nhỏ. Index không nhất thiết cải thiện nhiều trong tình huống như vậy.

Ví dụ “lấy mọi sản phẩm không phải phone” có thể trả về đa số collection. Nếu nghiệp vụ biết rõ các category cần hiển thị, đôi khi dùng điều kiện dương với `$in` giúp mô tả mục đích rõ hơn:

~~~javascript
// Điều kiện loại trừ:
{ category: { $ne: "phone" } }

// Điều kiện bao gồm cụ thể khi danh sách category có quy tắc rõ ràng:
{ category: { $in: ["laptop", "book", "accessory"] } }
~~~

Hai cách **không luôn tương đương** nếu có category mới hoặc field `category` bị thiếu. Chỉ thay thế khi contract nghiệp vụ cho phép.

### 11.4. Đọc explain thay vì đoán

Dùng `explain("executionStats")` để khảo sát:

~~~javascript
logicDb.products
  .find(orFilter)
  .explain("executionStats");
~~~

Các điểm cần quan sát gồm `winningPlan`, loại stage quét index/collection (chẳng hạn `IXSCAN` hoặc `COLLSCAN`), `totalKeysExamined`, `totalDocsExamined` và `nReturned` nếu phiên bản trả về các trường tương ứng.

Đối với pipeline:

~~~javascript
logicDb.products.explain("executionStats").aggregate([
  { $match: orFilter },
  { $sort: { price: -1 } },
  { $limit: 10 }
]);
~~~

Một index phù hợp với việc lọc và sắp xếp có thể hiệu quả hơn tạo nhiều index đơn lẻ không phục vụ được sort. Luôn đo trên dữ liệu đủ lớn và gần với phân bố thực tế trước khi điều chỉnh index.

## 12. Lỗi phổ biến khi ghép bộ lọc từ ứng dụng

| Sai lầm | Vì sao sai hoặc nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Lặp hai khóa `$or` trong cùng object | JavaScript giữ khóa cuối, mất nhóm điều kiện đầu | Dùng `$and: [{ $or: [...] }, { $or: [...] }]` |
| Viết `$not` ở cấp root filter | `$not` là query operator ở cấp field | Dùng `$nor` cho phủ định filter |
| Nhầm `$nor: [A, B]` với `NOT (A AND B)` | `$nor` phủ định **A OR B** | Dùng `$nor: [{...A..., ...B...}]` khi cần phủ định nhóm AND |
| Giả định `$not` chỉ khớp field tồn tại | Điều kiện phủ định có thể khớp tài liệu thiếu field | Thêm `$exists: true` nếu cần |
| Dùng `$or` cho nhiều giá trị bằng nhau của một field | Dài và khó bảo trì | Xem xét `$in` |
| Không kiểm soát kiểu dữ liệu | `"0"`, `0` và `null` có semantics khác nhau | Chuẩn hóa schema/BSON type, dùng validation |
| Giả định `$or` trả đúng thứ tự phần tử của mảng điều kiện | Logic không quy định thứ tự kết quả | Dùng `sort()` |
| Bỏ ngoặc logic khi đưa điều kiện ra/vào `$or` | Làm thay đổi phạm vi của từng điều kiện | Viết biểu thức A/B/C bằng lời trước |
| Tin rằng có index thì `$or` luôn nhanh | Một nhánh kém indexable có thể làm toàn truy vấn tốn chi phí | Dùng `explain` và đo workload thật |
| Chạy `updateMany()` với filter ghép chưa kiểm tra | Có thể sửa quá nhiều document | Dùng `find()`/`countDocuments()` đọc trước cùng filter |
| Dựa vào thứ tự điều kiện để tránh lỗi | Optimizer có thể đánh giá/biến đổi các điều kiện, không bảo đảm short-circuit như code ứng dụng | Thiết kế biểu thức an toàn với dữ liệu đầu vào |

**Lưu ý về lỗi đánh giá:** Một biểu thức `$expr` có phép toán không hợp lệ trên dữ liệu nào đó có thể gây lỗi ngay cả khi cùng filter còn một nhánh khác mà bạn kỳ vọng loại bỏ tài liệu đó. Không nên xem thứ tự trong mảng `$and` hoặc `$or` là một cơ chế bảo vệ chắc chắn trước lỗi như chia cho 0; hãy kiểm tra kiểu dữ liệu và viết biểu thức chịu được giá trị biên.

## 13. Bài tập thực hành có đối chiếu kết quả

Hãy dùng đúng bộ dữ liệu chín sản phẩm ở mục 2, trước khi chạy các ví dụ `updateMany()` có tác dụng ghi. Với mỗi bài, thử viết ít nhất hai cách khi phù hợp, rồi dùng `ids(filter)` để xem kết quả.

### Bài 1: AND với khoảng giá

Tìm laptop có giá từ 700 đến 1.500 và còn hàng. Sản phẩm nào được trả về?

Gợi ý:

~~~javascript
ids({
  category: "laptop",
  price: { $gte: 700, $lte: 1500 },
  stock: { $gt: 0 }
});
// ["p01"]
~~~

`p02` nằm trong khoảng giá nhưng hết hàng, còn `p06` vượt cận giá trên.

### Bài 2: OR giữa hai nhóm điều kiện

Tìm sản phẩm có `category: "book"` hoặc sản phẩm `category: "phone"` với `price < 600`.

~~~javascript
ids({
  $or: [
    { category: "book" },
    { category: "phone", price: { $lt: 600 } }
  ]
});
// ["p05", "p08"]
~~~

### Bài 3: NOR loại hai nhóm

Loại các sản phẩm `archived` và các sản phẩm đã hết hàng:

~~~javascript
ids({
  $nor: [
    { status: "archived" },
    { stock: 0 }
  ]
});
// ["p01", "p03", "p04", "p05", "p08", "p09"]
~~~

`p09` vẫn được giữ vì không có `status: "archived"` và `stock` lớn hơn 0.

### Bài 4: NOT và field missing

Tìm sản phẩm không đạt `rating >= 4.5`. Sau đó chỉ giữ các tài liệu có `rating` tồn tại.

~~~javascript
ids({ rating: { $not: { $gte: 4.5 } } });
// ["p02", "p07", "p08", "p09"]

ids({
  $and: [
    { rating: { $exists: true } },
    { rating: { $not: { $gte: 4.5 } } }
  ]
});
// ["p02", "p07", "p09"]
~~~

Giải thích vì sao `p08` xuất hiện ở truy vấn đầu nhưng không xuất hiện ở truy vấn sau.

### Bài 5: Hai OR kết hợp bằng AND

Tìm sản phẩm thuộc nhóm laptop hoặc phone **và** có brand ACME hoặc còn nhiều hơn 5 đơn vị:

~~~javascript
ids({
  $and: [
    {
      $or: [
        { category: "laptop" },
        { category: "phone" }
      ]
    },
    {
      $or: [
        { brand: "ACME" },
        { stock: { $gt: 5 } }
      ]
    }
  ]
});
// ["p01", "p03", "p06", "p08"]
~~~

Giải thích vì sao `p06` vẫn nằm trong kết quả dù đã `archived`: filter không hề yêu cầu trạng thái active.

### Bài 6: Phủ định một nhóm AND

Tìm tất cả tài liệu **trừ** những tài liệu đồng thời `category = "laptop"` và `stock > 0`:

~~~javascript
ids({
  $nor: [
    { category: "laptop", stock: { $gt: 0 } }
  ]
});
// ["p02", "p03", "p04", "p05", "p07", "p08", "p09"]
~~~

`p01` và `p06` bị loại vì là laptop còn hàng. `p02` dù là laptop vẫn được giữ vì `stock: 0`.

### Bài 7: Đọc và sửa lỗi filter

Một đồng nghiệp đưa đoạn code:

~~~javascript
var filter = {
  $or: [
    { status: "active" },
    { status: "draft" }
  ],
  $or: [
    { stock: { $gt: 0 } },
    { category: "book" }
  ]
};
~~~

Yêu cầu nghiệp vụ thực sự là:

~~~text
(status = active OR status = draft)
AND
(stock > 0 OR category = book)
~~~

Hãy viết lại bằng `$and` chứa hai `$or`. Trả lời điều gì xảy ra nếu dùng object `filter` ban đầu trong JavaScript.

## 14. Ghi nhớ cách chọn toán tử

Khi xây dựng một bộ lọc, hãy bắt đầu bằng **mô tả chính xác điều kiện nghiệp vụ**, đặc biệt với phép phủ định và trường có thể thiếu:

- **`$and`:** cần tất cả các biểu thức cùng đúng; khi chỉ có các field khác nhau, AND ngầm định thường đủ.
- **`$or`:** chỉ cần một biểu thức đúng; với nhiều lựa chọn trên một field, `$in` có thể rõ ràng hơn.
- **`$nor`:** không biểu thức con nào được đúng; phù hợp với phủ định nhóm filter, kể cả biểu thức chứa nhiều field.
- **`$not`:** phủ định điều kiện toán tử của **một field**; cần lưu ý document không chứa field.
- **`$exists`:** dùng để quyết định rõ dữ liệu thiếu field có thuộc phạm vi của truy vấn phủ định hay không.

Các toán tử này có thể lồng nhau để biểu diễn logic phức tạp. Sau khi viết filter, hãy kiểm tra bằng bộ dữ liệu nhỏ có **trường hợp đúng, sai, biên và field missing**, rồi dùng `explain` để đánh giá hiệu năng trên tập dữ liệu thực tế.

### Tài liệu tham khảo chính thức

- [MongoDB Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/) — cú pháp filter và điều kiện truy vấn.
- [`$and` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/and/) — AND tường minh và AND ngầm định.
- [`$or` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/or/) — nhiều nhánh điều kiện và lưu ý về index.
- [`$nor` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/nor/) — phủ định OR và hành vi với field không tồn tại.
- [`$not` — Logical Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/not/) — phủ định biểu thức ở cấp field.
- [`$exists` — Element Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — kiểm tra sự tồn tại của trường.
- [`$elemMatch` — Array Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — kết hợp điều kiện trên cùng phần tử mảng.
