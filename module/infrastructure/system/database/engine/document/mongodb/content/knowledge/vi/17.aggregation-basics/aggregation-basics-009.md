# Thay đổi document gốc bằng $replaceRoot và $replaceWith trong MongoDB

## 1. Bài toán: khi document đầu vào không phải hình dạng đầu ra mong muốn

MongoDB lưu dữ liệu trong các **document BSON**. Một document có thể chứa object lồng nhau, mảng và các trường mô tả nhiều phần của một thực thể. Cấu trúc tối ưu để lưu trữ không phải lúc nào cũng là cấu trúc mà một API, báo cáo hoặc bước xử lý tiếp theo cần nhận.

Ví dụ document đơn hàng:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  orderNo: "ORDER-1001",
  status: "PAID",
  shipping: {
    recipient: "An",
    city: "Hà Nội",
    postalCode: "100000"
  },
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 120000 },
    { sku: "PEN-01", quantity: 3, unitPrice: 10000 }
  ]
}
```

Ứng dụng có thể cần ba kiểu đầu ra:

1. **Chỉ lấy thông tin giao hàng**: kết quả có `recipient`, `city`, `postalCode` ngay ở cấp cao nhất, không có phần `shipping` bọc ngoài.
2. **Mỗi dòng hàng thành một document riêng**: đầu ra có `sku`, `quantity`, `unitPrice` và một vài thông tin đơn hàng cần thiết.
3. **Ghép thông tin từ nhiều nguồn**: tạo một document kết quả có cấu trúc khác hẳn document ban đầu.

Trong aggregation pipeline, hai stage giải quyết bài toán **thay toàn bộ document gốc hiện tại** là:

- `$replaceRoot` — viết biểu thức dưới thuộc tính `newRoot`.
- `$replaceWith` — viết trực tiếp biểu thức tạo document mới.

Chúng có cùng mục đích, khác chủ yếu ở cú pháp. **Root document** ở đây là document mà **một stage của pipeline đang xử lý**, không có nghĩa là tự động ghi đè document đang lưu trong collection.

Bài này giúp bạn:

- Hiểu khái niệm root document và điểm khác biệt với việc sửa trường bằng `$set` hoặc chọn trường bằng `$project`.
- Viết hai stage `$replaceRoot` và `$replaceWith` tương đương.
- Đưa object lồng nhau lên cấp cao nhất, thay document gốc bằng document tự dựng và giữ lại field cần thiết.
- Kết hợp `$unwind`, `$group`, `$lookup` với thao tác thay root.
- Xử lý object thiếu, `null`, sai kiểu và mảng để pipeline không lỗi bất ngờ.
- Phân biệt thay root ở pipeline chỉ đọc với việc cập nhật document thật bằng update pipeline.

## 2. Root document là gì?

### 2.1. Document đi qua các stage

Aggregation pipeline là chuỗi các stage:

```text
Collection
    |
    v
$match  --> $project --> $replaceWith --> $sort
    |         |             |            |
    v         v             v            v
Document ở mỗi bước có thể có hình dạng khác nhau
```

Một stage nhận document từ stage trước và đưa document đến stage sau. “Root” là **object cấp cao nhất hiện tại** của document ở vị trí đó.

Giả sử document ban đầu:

```javascript
{
  _id: "ORDER-1001",
  status: "PAID",
  shipping: {
    recipient: "An",
    city: "Hà Nội"
  }
}
```

Khi pipeline nhận document này:

- `$_id` truy cập field `_id` của root hiện tại.
- `$shipping` truy cập object `shipping` ở root.
- `$shipping.city` truy cập trường `city` bên trong `shipping`.
- `$$ROOT` là biến hệ thống đại diện cho **toàn bộ document gốc ở stage hiện tại**.

Sau một stage thay root bằng `shipping`:

```javascript
{
  recipient: "An",
  city: "Hà Nội"
}
```

Từ stage sau, `$city` truy cập thành phố trực tiếp; `$shipping.city` không còn tồn tại, vì `shipping` đã không còn là một object bao ngoài. `_id` và `status` cũng không tự động được giữ.

### 2.2. Thay root là thay toàn bộ hình dạng

Khi dùng `$replaceRoot` hoặc `$replaceWith`, document cũ **được thay hoàn toàn** bằng giá trị object mà biểu thức trả về. MongoDB không tự trộn hai object, cũng không tự giữ `_id`.

Điều này khác với:

```javascript
{ $set: { city: "$shipping.city" } }
```

`$set` thêm hoặc thay đổi field `city` trong document hiện có, trong khi các field khác vẫn còn (trừ khi được sửa/xóa bởi stage khác).

### 2.3. Thay root không mặc định ghi vào collection

```javascript
db.orders.aggregate([
  { $replaceWith: "$shipping" }
]);
```

Một pipeline `aggregate()` đọc và trả kết quả đã biến đổi. **Document được lưu trong `db.orders` không thay đổi** chỉ vì có `$replaceWith` hoặc `$replaceRoot` trong pipeline đọc.

Để ghi kết quả aggregation ra collection cần cơ chế ghi riêng như `$merge` hoặc `$out`, với quyền và quy trình quản lý phù hợp. Ngoài ra, MongoDB hỗ trợ **aggregation pipeline update** với một số stage, bao gồm thay root, để cập nhật document thực sự; trường hợp này được phân biệt ở phần sau.

## 3. Cú pháp của $replaceRoot và $replaceWith

### 3.1. `$replaceRoot`

Cú pháp:

```javascript
{
  $replaceRoot: {
    newRoot: <expression>
  }
}
```

`<expression>` có thể là:

- đường dẫn tới một object lồng trong document, như `"$shipping"`;
- một object được dựng từ các field cũ;
- biểu thức trả về document, như `$mergeObjects`;
- kết quả biểu thức điều kiện trả về một object.

Ví dụ:

```javascript
db.orders.aggregate([
  {
    $replaceRoot: {
      newRoot: "$shipping"
    }
  }
]);
```

Ở stage này, `newRoot` phải được tính ra **một document (object)** cho mỗi đầu vào đi qua stage.

### 3.2. `$replaceWith`

Cú pháp:

```javascript
{
  $replaceWith: <expression>
}
```

Ví dụ:

```javascript
db.orders.aggregate([
  {
    $replaceWith: "$shipping"
  }
]);
```

Đây là dạng ngắn hơn, không cần tên thuộc tính `newRoot`. `$replaceWith` về chức năng là cách viết thay thế cho `$replaceRoot` trong nhiều trường hợp.

### 3.3. Hai stage tương đương

Hai pipeline sau biểu đạt cùng một biến đổi:

```javascript
// Cách A.
db.orders.aggregate([
  { $replaceRoot: { newRoot: "$shipping" } }
]);

// Cách B.
db.orders.aggregate([
  { $replaceWith: "$shipping" }
]);
```

Với cùng tài liệu đầu vào và cùng biểu thức, **hai stage có cùng yêu cầu về kiểu kết quả và cách xử lý lỗi**. Không có stage nào tự sửa dữ liệu gốc, tự chặn `null` hoặc tự giữ `_id`.

### 3.4. Bảng so sánh nhanh

| Đặc điểm | `$replaceRoot` | `$replaceWith` |
| --- | --- | --- |
| Cú pháp | `{ $replaceRoot: { newRoot: expr } }` | `{ $replaceWith: expr }` |
| Giá trị biểu thức cần trả về | Document | Document |
| Thay toàn bộ root hiện tại | Có | Có |
| Tự giữ `_id` | Không | Không |
| Dùng để đưa nested object lên root | Có | Có |
| Dùng với `$mergeObjects` | Có | Có |
| Thực thi trên object thiếu/`null`/kiểu không phải object | Có thể lỗi | Có thể lỗi |
| Trong `aggregate()` thuần đọc có sửa collection không? | Không | Không |

## 4. Tạo dữ liệu thực hành bằng mongosh

Các ví dụ sử dụng database thử nghiệm riêng `mongo_replace_root_row186_lab` và hai collection `orders_demo`, `customers_demo`. Hãy kết nối đến MongoDB được phép sử dụng trước khi chạy. Ví dụ:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Thay URI theo host, TLS và xác thực của môi trường bạn. Trong `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_replace_root_row186_lab");
const orders = lab.getCollection("orders_demo");
const customers = lab.getCollection("customers_demo");

const runId = "row186-" + new ObjectId().toHexString();
const anId = new ObjectId();
const binhId = new ObjectId();

customers.insertMany([
  {
    _id: anId,
    runId,
    displayName: "Nguyễn An",
    tier: "GOLD"
  },
  {
    _id: binhId,
    runId,
    displayName: "Trần Bình",
    tier: "SILVER"
  }
]);

const order1Id = new ObjectId();
const order2Id = new ObjectId();
const order3Id = new ObjectId();
const order4Id = new ObjectId();

orders.insertMany([
  {
    _id: order1Id,
    runId,
    orderNo: "ORDER-186-01",
    customerId: anId,
    status: "PAID",
    createdAt: ISODate("2026-11-10T02:00:00Z"),
    totalAmount: 270000,
    shipping: {
      recipient: "An",
      city: "Hà Nội",
      postalCode: "100000"
    },
    items: [
      { sku: "BOOK-01", quantity: 2, unitPrice: 120000 },
      { sku: "PEN-01", quantity: 3, unitPrice: 10000 }
    ]
  },
  {
    _id: order2Id,
    runId,
    orderNo: "ORDER-186-02",
    customerId: binhId,
    status: "NEW",
    createdAt: ISODate("2026-11-11T03:00:00Z"),
    totalAmount: 99000,
    shipping: {
      recipient: "Bình",
      city: "Đà Nẵng",
      postalCode: "550000"
    },
    items: [
      { sku: "NOTE-01", quantity: 1, unitPrice: 99000 }
    ]
  },
  {
    _id: order3Id,
    runId,
    orderNo: "ORDER-186-03",
    customerId: anId,
    status: "DRAFT",
    createdAt: ISODate("2026-11-12T04:00:00Z"),
    totalAmount: 0,
    shipping: null,
    items: []
  },
  {
    _id: order4Id,
    runId,
    orderNo: "ORDER-186-04",
    customerId: anId,
    status: "DRAFT",
    createdAt: ISODate("2026-11-13T05:00:00Z"),
    totalAmount: 0,
    items: []
    // Cố ý không có field shipping.
  }
]);

print("database=" + lab.getName());
print("runId=" + runId);
print("orders=" + orders.countDocuments({ runId }));
```

Hai order đầu có object `shipping`, order thứ ba có `shipping: null`, order thứ tư thiếu field `shipping`. Dữ liệu này giúp quan sát rõ vấn đề của việc đưa object con lên root.

Các ví dụ phía dưới giả định **cùng phiên `mongosh`**, nơi các biến `lab`, `orders`, `customers`, `runId` và các ID vẫn còn. Đừng truy vấn/xóa bằng `runId` đoán lại khi đã mở một phiên mới.

## 5. Đưa object lồng nhau lên root

### 5.1. Trường hợp đơn giản: mọi document đều có object hợp lệ

Ta chỉ chọn những order có `shipping` là object:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceRoot: {
      newRoot: "$shipping"
    }
  }
]);
```

Hai document kết quả có dạng:

```javascript
{
  recipient: "An",
  city: "Hà Nội",
  postalCode: "100000"
}
{
  recipient: "Bình",
  city: "Đà Nẵng",
  postalCode: "550000"
}
```

Điểm cần quan sát:

- `shipping` không còn là object bọc ngoài.
- Các field `recipient`, `city`, `postalCode` trở thành field ở root.
- `_id` của order không còn trong document kết quả.
- `orderNo`, `status`, `customerId` và `runId` cũng không được tự động giữ.

Đây là hành vi cố ý của **thay toàn bộ root**.

### 5.2. Viết tương đương bằng `$replaceWith`

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  { $replaceWith: "$shipping" }
]);
```

Không cần đổi dữ liệu đầu vào hoặc bộ lọc khi chuyển giữa hai stage. Chỉ thay cú pháp tạo root.

### 5.3. Vì sao dùng `$expr + $type` ở trước?

Biểu thức:

```javascript
{
  $expr: {
    $eq: [{ $type: "$shipping" }, "object"]
  }
}
```

kiểm tra giá trị field trong **document hiện tại** có kiểu BSON object. Nhờ đó:

- Document có `shipping` là object đi tiếp.
- Document có `shipping: null` bị loại khỏi luồng.
- Document thiếu `shipping` bị loại.
- Document có `shipping` là string, number hoặc array không bị đưa trực tiếp vào stage thay root.

Điều này khác một số phép khớp theo trường trong query có thể xét cả phần tử mảng. Với yêu cầu bảo vệ biểu thức thay root khỏi giá trị không phải object, kiểm tra loại của **giá trị biểu thức** là cách thể hiện rõ ràng.

## 6. Điều gì xảy ra khi field thiếu hoặc không phải document?

### 6.1. Trường hợp gây lỗi

Nếu chạy pipeline sau trên cả bốn order:

```javascript
// Ví dụ CÓ THỂ GÂY LỖI vì có shipping null/missing.
orders.aggregate([
  { $match: { runId } },
  { $replaceWith: "$shipping" }
]);
```

Stage thay root yêu cầu biểu thức trả về document hợp lệ. Khi `$shipping` là `null`, không tồn tại hoặc có kiểu như string/array, aggregation có thể thất bại thay vì trả một document rỗng.

MongoDB không tự diễn giải `null` thành `{}`, không tự biến mảng thành nhiều document và không tự bỏ qua document lỗi ở stage này.

### 6.2. Hướng xử lý 1: lọc trước

Nếu yêu cầu chỉ cần những document **thực sự có shipping hợp lệ**:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  { $replaceWith: "$shipping" }
]);
```

Cách này làm mất các order không có thông tin shipping khỏi kết quả **của pipeline**, nhưng không xóa chúng khỏi collection.

### 6.3. Hướng xử lý 2: dùng giá trị mặc định cho null/missing

Khi dữ liệu được quy ước `shipping` chỉ có thể là object, `null` hoặc missing, có thể dùng `$ifNull`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      $ifNull: [
        "$shipping",
        {
          recipient: "Chưa cung cấp",
          city: "Chưa xác định"
        }
      ]
    }
  }
]);
```

Với order có `shipping: null` hoặc thiếu field, kết quả là object mặc định. Nhưng nếu `shipping` chứa **chuỗi**, `$ifNull` vẫn trả chuỗi đó vì nó không phải null. Khi đó `$replaceWith` vẫn có thể lỗi.

Do đó:

> `$ifNull` giải quyết null/missing, **không phải** bộ kiểm tra mọi kiểu dữ liệu.

### 6.4. Hướng xử lý 3: kiểm tra type và fallback

Để bảo vệ cả giá trị sai kiểu:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      $cond: {
        if: {
          $eq: [{ $type: "$shipping" }, "object"]
        },
        then: "$shipping",
        else: {
          recipient: "Chưa cung cấp",
          city: "Chưa xác định"
        }
      }
    }
  }
]);
```

Ở đây cả hai nhánh của `$cond` đều phải đưa ra một document. Nếu nhánh `then` nhận object, nó được dùng; các loại khác đi qua object mặc định.

Trong hệ thống thật, nên phân biệt:

- **Thiếu dữ liệu hợp lệ theo nghiệp vụ** → fallback có thể phù hợp.
- **Dữ liệu sai schema** → đôi khi phải báo lỗi, sửa parser hoặc migration thay vì âm thầm che giấu.

Fallback giúp pipeline bền vững, nhưng không thay thế quản trị chất lượng dữ liệu.

## 7. Giữ lại thông tin root cũ bằng $mergeObjects

### 7.1. Vấn đề mất thông tin

Sau khi dùng `$replaceWith: "$shipping"`, API chỉ còn địa chỉ. Nếu muốn nhận:

```javascript
{
  orderId: ObjectId("..."),
  orderNo: "ORDER-186-01",
  status: "PAID",
  recipient: "An",
  city: "Hà Nội",
  postalCode: "100000"
}
```

thì phải **tự đưa các trường order cần giữ vào root mới**.

Một toán tử aggregation phù hợp là `$mergeObjects`.

### 7.2. `$mergeObjects` làm gì?

`$mergeObjects` nhận các object và tạo object kết hợp. Khi hai object có cùng field, **giá trị từ object đứng sau ghi đè giá trị đứng trước**. Các operand `null` được bỏ qua theo ngữ nghĩa của `$mergeObjects`.

Ví dụ:

```javascript
{
  $mergeObjects: [
    { city: "Chưa xác định", active: false },
    { city: "Hà Nội", recipient: "An" },
    { active: true }
  ]
}
```

Kết quả biểu thức:

```javascript
{
  city: "Hà Nội",
  active: true,
  recipient: "An"
}
```

Thứ tự operand vì thế rất quan trọng khi có tên field trùng.

### 7.3. Đưa shipping lên root nhưng giữ các field cần thiết

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$shipping",
          {
            orderId: "$_id",
            orderNo: "$orderNo",
            status: "$status",
            createdAt: "$createdAt"
          }
        ]
      }
    }
  }
]);
```

Object được dựng từ field của order nằm **sau** `"$shipping"`. Nếu dữ liệu shipping tình cờ có tên field `status` hoặc `orderNo`, giá trị của order sẽ ưu tiên theo thứ tự merge này.

Kết quả có các field shipping lẫn metadata order, nhưng không còn object `shipping` lồng bên trong và không tự có `_id`. Trường `orderId` được đặt rõ ràng để giữ ID order dưới tên mới.

### 7.4. Giữ lại chính `_id`

Nếu API cần `_id` của order trong kết quả:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$shipping",
        {
          _id: "$_id",
          orderNo: "$orderNo",
          status: "$status"
        }
      ]
    }
  }
]);
```

MongoDB chỉ giữ `_id` vì bạn **đã thêm trường đó vào object mới**. Nếu không thêm, kết quả mới có thể không có `_id`.

### 7.5. Dùng default object để tránh thiếu trường

Nếu muốn trả một document cho mọi order, kể cả khi không có shipping:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      $mergeObjects: [
        {
          recipient: "Chưa cung cấp",
          city: "Chưa xác định"
        },
        {
          $cond: [
            { $eq: [{ $type: "$shipping" }, "object"] },
            "$shipping",
            {}
          ]
        },
        {
          orderId: "$_id",
          orderNo: "$orderNo",
          status: "$status"
        }
      ]
    }
  }
]);
```

Ba operand có chức năng riêng:

1. **Default** — cung cấp field tối thiểu.
2. **Shipping object nếu hợp lệ** — ghi đè default bằng dữ liệu thực tế.
3. **Metadata từ order** — bổ sung các trường bắt buộc của output.

Nếu chỉ cần xử lý null/missing và chắc chắn không có giá trị kiểu khác, có thể thay `$cond` bằng `{ $ifNull: ["$shipping", {}] }`. Khi dữ liệu có thể bị trộn kiểu, kiểm tra `$type` giúp bảo đảm toán tử merge không nhận string/array.

## 8. Giữ cả document gốc rồi “làm phẳng” một phần

Đôi khi yêu cầu không phải bỏ hết field cũ mà là đưa các field shipping lên top-level **đồng thời vẫn giữ field khác**.

### 8.1. Dùng `$$ROOT`

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$$ROOT",
        "$shipping"
      ]
    }
  }
]);
```

Ở stage thay root, `$$ROOT` đại diện toàn bộ document hiện tại. Sau đó `$shipping` được merge lên ngoài. Các field gốc như `orderNo`, `items` vẫn còn và các field shipping cũng được thêm ở root.

Ví dụ:

```javascript
{
  _id: ObjectId("..."),
  orderNo: "ORDER-186-01",
  status: "PAID",
  shipping: {
    recipient: "An",
    city: "Hà Nội",
    postalCode: "100000"
  },
  recipient: "An",
  city: "Hà Nội",
  postalCode: "100000",
  items: [/* ... */]
}
```

Đây là **sao chép thông tin lồng ra ngoài**, không phải tự động loại field nested. Object `shipping` vẫn tồn tại.

### 8.2. Bỏ object nested sau khi đưa lên ngoài

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      $expr: {
        $eq: [{ $type: "$shipping" }, "object"]
      }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: ["$$ROOT", "$shipping"]
    }
  },
  { $unset: "shipping" }
]);
```

`$unset` loại field `shipping` khỏi document kết quả của pipeline. Trong thực tế, cần cân nhắc nguy cơ **trùng tên field**: nếu object shipping có field `status`, merge sau sẽ ghi đè status của order. Để có hợp đồng đầu ra ổn định và an toàn, đôi khi dựng object đích tường minh bằng `$project` hoặc `$replaceWith` đơn giản hơn.

## 9. Dùng $replaceWith để dựng document mới theo hợp đồng API

Không nhất thiết phải lấy nguyên một object con. `$replaceWith` chấp nhận một biểu thức object do bạn tự dựng:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      orderId: "$_id",
      code: "$orderNo",
      state: "$status",
      amount: "$totalAmount",
      orderedAt: "$createdAt",
      city: {
        $ifNull: ["$shipping.city", "Chưa xác định"]
      },
      label: {
        $concat: ["Đơn ", "$orderNo"]
      }
    }
  },
  { $sort: { orderedAt: -1 } }
]);
```

Object được dựng mới có:

- `orderId` lấy từ `_id`.
- `code` đổi tên từ `orderNo`.
- `state` đổi tên từ `status`.
- `amount` đổi tên từ `totalAmount`.
- `orderedAt` đổi tên từ `createdAt`.
- `city` được lấy từ object con và có fallback.
- `label` được tạo bằng biểu thức `$concat`.

Sau `$replaceWith`, stage `$sort` phải dùng tên field mới là `orderedAt`, không còn `createdAt` ở output. Đây là ảnh hưởng rất thường gặp khi thay root ở giữa pipeline.

### 9.1. Giá trị hằng và tên field bắt đầu bằng ký tự đặc biệt

Khi viết expression, chuỗi bắt đầu bằng `$` có thể được hiểu là **field path** hoặc cú pháp biểu thức. Nếu muốn lưu literal như `"$10 voucher"`, dùng `$literal`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      promotionLabel: { $literal: "$10 voucher" }
    }
  }
]);
```

Một object trả về từ `$replaceWith` vẫn phải là document hợp lệ theo các quy tắc về field name và BSON. Không dùng biểu thức tạo scalar ở top-level của stage thay root.

## 10. Kết hợp $unwind để biến phần tử mảng thành root

### 10.1. Vì sao cần `$unwind`?

Một document order có nhiều dòng hàng:

```javascript
{
  orderNo: "ORDER-186-01",
  items: [
    { sku: "BOOK-01", quantity: 2, unitPrice: 120000 },
    { sku: "PEN-01", quantity: 3, unitPrice: 10000 }
  ]
}
```

Nếu đưa trực tiếp `$items` vào root:

```javascript
// Không phải cách đúng để tạo một document cho mỗi item.
{ $replaceWith: "$items" }
```

`$items` là **mảng**, không phải document. Stage thay root yêu cầu object, vì vậy không thể coi mảng là nhiều root chỉ nhờ `$replaceWith`.

Muốn **mỗi phần tử mảng trở thành một document đầu ra**, trước hết dùng `$unwind`:

```text
Order (items = [A, B])
          |
       $unwind
        /    \
       v      v
 Order+A    Order+B
       |      |
       +-- $replaceWith: "$items"
             |
             v
        Item A, Item B
```

### 10.2. Mỗi dòng hàng thành một root

```javascript
orders.aggregate([
  { $match: { runId } },
  { $unwind: "$items" },
  { $replaceWith: "$items" }
]);
```

Kết quả từ dữ liệu mẫu:

```javascript
{ sku: "BOOK-01", quantity: 2, unitPrice: 120000 }
{ sku: "PEN-01", quantity: 3, unitPrice: 10000 }
{ sku: "NOTE-01", quantity: 1, unitPrice: 99000 }
```

Các order có `items: []` không đóng góp phần tử vào kết quả với hành vi mặc định của `$unwind`. Sau `$unwind`, `$items` là object của một dòng hàng, nên thay root hợp lệ.

### 10.3. Vừa tách dòng hàng vừa giữ thông tin order

Nếu muốn mỗi item có mã đơn hàng để tiếp tục xử lý:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $unwind: "$items" },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$items",
          {
            orderId: "$_id",
            orderNo: "$orderNo",
            orderStatus: "$status",
            createdAt: "$createdAt"
          }
        ]
      }
    }
  },
  { $sort: { orderNo: 1, sku: 1 } }
]);
```

Kết quả sẽ có các field của item cùng `orderId`, `orderNo`, `orderStatus`. Việc đặt metadata order ở cuối `$mergeObjects` khiến các field tương ứng của order được ưu tiên khi có trùng tên.

Nếu mỗi item có `_id` riêng, cần phân biệt ID item với ID order: nên dùng những tên rõ như `orderId` và `lineItemId`, không mặc nhiên giữ `_id` trong mọi bước flatten.

### 10.4. Phần tử mảng không phải object

Nếu `items` là mảng string như `["A","B"]`, sau `$unwind` mỗi `$items` là string; `$replaceWith: "$items"` lại không hợp lệ. Khi mảng chứa các giá trị primitive, hãy **bọc thành object**:

```javascript
db.catalog.aggregate([
  { $unwind: "$tags" },
  {
    $replaceWith: {
      sourceId: "$_id",
      tag: "$tags"
    }
  }
]);
```

Ví dụ trên minh họa mảng tag ở collection giả định `catalog`; vì root mới được **dựng thành object**, giá trị `tags` là string không gây lỗi kiểu root. Quy tắc tổng quát: biểu thức ở `$replaceWith` phải trả về object, không phụ thuộc kiểu của từng field bên trong object đó.

## 11. Kết hợp $group để chuyển key nhóm thành field ở root

Một pipeline báo cáo thường có `$group`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: {
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$totalAmount" }
    }
  }
]);
```

Kết quả có cấu trúc:

```javascript
{
  _id: { status: "PAID" },
  orderCount: 1,
  totalAmount: 270000
}
```

Nếu báo cáo muốn `status` là field top-level, không phải `_id.status`:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: {
        status: "$status"
      },
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$totalAmount" }
    }
  },
  {
    $replaceWith: {
      $mergeObjects: [
        "$_id",
        {
          orderCount: "$orderCount",
          totalAmount: "$totalAmount"
        }
      ]
    }
  },
  { $sort: { status: 1 } }
]);
```

Đầu ra:

```javascript
{
  status: "PAID",
  orderCount: 1,
  totalAmount: 270000
}
```

Trong bước `$group`, `_id` được tạo thành **object** nên có thể merge. Nếu group key chỉ là scalar, ví dụ `_id: "$status"`, thì `$replaceWith: "$_id"` sẽ **không hợp lệ**, bởi string `"PAID"` không phải document. Khi đó bọc scalar bằng một object:

```javascript
{
  $replaceWith: {
    status: "$_id",
    orderCount: "$orderCount"
  }
}
```

Việc dựng object rõ ràng cũng giúp kiểm soát field nào xuất hiện trong báo cáo.

## 12. Kết hợp $lookup với $unwind và thay root

### 12.1. Dữ liệu kết hợp thường nằm trong mảng

Với đơn hàng có `customerId`, `$lookup` đến `customers_demo` sẽ tạo field `customer` dạng **mảng document**, ngay cả khi mỗi `customerId` khớp tối đa một khách hàng.

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $lookup: {
      from: "customers_demo",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
```

Kết quả vẫn có toàn bộ order và thêm:

```javascript
customer: [
  {
    _id: ObjectId("..."),
    runId: "row186-...",
    displayName: "Nguyễn An",
    tier: "GOLD"
  }
]
```

Không thể đưa `"$customer"` trực tiếp vào root, vì đây là mảng. Cần xử lý kiểu mảng trước.

### 12.2. Lấy một customer và kết hợp với metadata order

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $lookup: {
      from: "customers_demo",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $unwind: "$customer" },
  {
    $replaceWith: {
      $mergeObjects: [
        "$customer",
        {
          orderId: "$_id",
          orderNo: "$orderNo",
          orderStatus: "$status",
          orderAmount: "$totalAmount"
        }
      ]
    }
  },
  {
    $project: {
      _id: 0,
      orderId: 1,
      orderNo: 1,
      orderStatus: 1,
      orderAmount: 1,
      displayName: 1,
      tier: 1
    }
  }
]);
```

Giải thích:

1. `$match` giới hạn order của lượt thực hành.
2. `$lookup` ghép theo `customerId` với `customers_demo._id`.
3. `$unwind` biến mảng `customer` thành một object trên mỗi kết quả.
4. `$mergeObjects` tạo root gồm thông tin customer và metadata order.
5. `$project` chọn đúng field API cần, tránh vô tình trả toàn bộ dữ liệu khách hàng.

Nếu một order không khớp customer, `$unwind` mặc định sẽ loại order đó. Nếu cần giữ order khi thiếu customer, có thể dùng `preserveNullAndEmptyArrays: true` rồi tạo fallback bằng `$mergeObjects` hoặc biểu thức điều kiện. Cần quyết định chính sách dữ liệu thiếu dựa trên nghiệp vụ, không mặc định bỏ qua hoặc chấp nhận.

### 12.3. Cần tránh xung đột tên field

Sau `$lookup`, customer cũng có `_id`, còn order có `_id`. Nếu dùng `$mergeObjects: ["$$ROOT", "$customer"]`, field `_id` của customer có thể ghi đè `_id` của order.

Để rõ ràng, nên:

- đặt `orderId` riêng từ `$_id` trước khi đưa customer lên root;
- đặt `customerId` theo đúng khóa customer;
- dùng `$project` hoặc object tường minh khi có field trùng;
- bảo đảm API không nhầm `_id` của order với `_id` của customer.

## 13. So sánh $replaceRoot/$replaceWith với các stage khác

| Stage | Vai trò chính | Có thay toàn bộ root không? |
| --- | --- | --- |
| `$project` | Chọn, bỏ, đổi tên hoặc tính field trong document đầu ra | Tạo hình dạng được chỉ định, nhưng không có cú pháp “lấy nguyên object con làm root” như `$replaceWith` |
| `$set` / `$addFields` | Thêm hoặc ghi đè field trong document hiện tại | Không mặc định loại các field khác |
| `$unset` | Loại bỏ field | Không thay toàn bộ document bằng một object khác |
| `$replaceRoot` | Thay root bằng biểu thức ở `newRoot` | Có |
| `$replaceWith` | Thay root bằng biểu thức trực tiếp | Có |
| `$unwind` | Tách mỗi phần tử mảng thành một document đi tiếp | Không tự đưa phần tử lên root |
| `$group` | Gom document và tính kết quả theo nhóm | Tạo document nhóm, thường có `_id` là khóa nhóm |

Ví dụ ba cách tạo đầu ra có ý nghĩa khác nhau:

```javascript
// A: thêm field ở cấp root, còn giữ phần lớn field cũ.
{
  $set: {
    city: "$shipping.city"
  }
}

// B: chỉ xuất một số field đã chọn.
{
  $project: {
    _id: 0,
    orderNo: 1,
    city: "$shipping.city"
  }
}

// C: dùng nguyên object shipping làm root.
{
  $replaceWith: "$shipping"
}
```

Chọn stage theo hợp đồng đầu ra:

- Muốn **chỉnh một vài field**: `$set` có thể trực quan hơn.
- Muốn **chọn một số field cố định**: `$project` dễ kiểm soát.
- Muốn **đưa một object lồng hoặc object kết hợp lên làm toàn bộ root**: `$replaceRoot`/`$replaceWith` là lựa chọn phù hợp.

Không cần dùng `$replaceWith` cho mọi bài toán chỉ vì cú pháp ngắn. Số stage, chi phí tính toán, khả năng đọc code và rủi ro mất field đều quan trọng.

## 14. Thứ tự stage và khả năng sử dụng index

### 14.1. Lọc sớm khi có thể

Khi pipeline chỉ cần document của một tenant hoặc một trạng thái, thường nên lọc sớm bằng field gốc trước khi thay root:

```javascript
orders.aggregate([
  {
    $match: {
      runId,
      status: "PAID"
    }
  },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      city: "$shipping.city",
      amount: "$totalAmount"
    }
  }
]);
```

Lý do:

- `$match` trên field ban đầu có thể khai thác index nếu index phù hợp.
- Số document cần biến đổi ít hơn.
- Sau `$replaceWith`, các tên field/đường dẫn cũ có thể không còn, nên filter phải được sửa theo hình dạng mới.

Ví dụ nếu root đã bị thay bằng `shipping`, một stage sau như `{$match:{status:"PAID"}}` không khớp theo ý định vì `status` không còn trong kết quả.

MongoDB có thể tối ưu lại thứ tự một số stage trong pipeline khi an toàn. Tuy nhiên, không nên dựa vào việc optimizer tự phục hồi các field đã bị loại hoặc biến đổi.

### 14.2. Thay root có dùng index trực tiếp không?

`$replaceWith` là stage biến đổi cấu trúc document, không phải một loại index. Index thường giúp các giai đoạn chọn/lọc/sắp xếp nếu điều kiện thích hợp. Việc thay root có thể buộc engine phải đọc các field không nằm trong index; nó không tự làm truy vấn được cover.

Ví dụ index trên `{runId:1,status:1}` có thể hữu ích cho `$match` tương ứng. Nhưng nếu `$replaceWith` cần toàn bộ object `shipping` mà index không chứa nội dung đó, MongoDB có thể phải đọc document gốc.

Trong hệ thống thật, dùng `explain("executionStats")` để xem số document/khóa index được quét, plan được chọn và các bước thực thi. Một pipeline có nhiều stage không nhất thiết chậm; chi phí phụ thuộc số lượng document, kích thước dữ liệu và cách index phục vụ đầu vào.

### 14.3. Sắp xếp trước hay sau khi thay root?

Nếu chỉ cần giữ thứ tự theo thời gian gốc:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $sort: { createdAt: -1 } },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      city: "$shipping.city"
    }
  }
]);
```

Sort theo `createdAt` trước khi field bị bỏ khỏi document. Nếu muốn sort sau, hãy giữ một field đầu ra chứa giá trị cần sort, ví dụ `orderedAt: "$createdAt"` rồi dùng `$sort: {orderedAt:-1}`.

## 15. Phân biệt aggregation đọc với update pipeline ghi

### 15.1. Một stage không tự thay collection

Lệnh:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $replaceWith: { orderNo: "$orderNo" } }
]);
```

trả các document chỉ có `orderNo`, nhưng sau đó:

```javascript
orders.findOne({ _id: order1Id });
```

vẫn trả document đã lưu với các field `_id`, `status`, `shipping`, `items`... như trước. Đây là **thay root trong luồng kết quả**, không phải cập nhật bền vững.

### 15.2. Aggregation pipeline update có thể thay document lưu

MongoDB còn hỗ trợ dùng một pipeline update với tập stage được phép, trong đó có `$replaceRoot`/`$replaceWith`. Trong trường hợp này, document cuối của pipeline update sẽ được dùng để cập nhật dữ liệu lưu.

Ví dụ **chỉ trên collection thử nghiệm**:

```javascript
orders.updateOne(
  {
    _id: order1Id,
    runId
  },
  [
    {
      $replaceWith: {
        $mergeObjects: [
          "$$ROOT",
          {
            note: "Đã xem xét cấu trúc",
            updatedAt: "$$NOW"
          }
        ]
      }
    }
  ]
);
```

Pipeline này dùng `$$ROOT` để giữ những field cũ và thêm `note`, `updatedAt`. Vì chạy qua `updateOne`, nó **thay đổi document đã lưu**; hoàn toàn khác với ví dụ `aggregate()` chỉ đọc. `$$NOW` là biến thời gian được MongoDB cấp cho phép xử lý, không phải chuỗi literal.

Những điều cần cẩn trọng trong update pipeline:

- `_id` là field bất biến của document; không được vô tình thay hoặc loại `_id` khi cập nhật document đã tồn tại.
- Schema validation và các index vẫn áp dụng theo quy tắc ghi của collection.
- Việc bỏ field khi thay root trong update có thể làm mất dữ liệu thật, không chỉ thay hình dạng API.
- Nếu nhiều document cần update, cần giới hạn bộ lọc và thiết kế migration/retry an toàn.
- Không chạy cập nhật thay root trên production chỉ để thử một aggregation.

### 15.3. Khi nào cần `$merge` hoặc `$out`?

Nếu muốn lấy kết quả aggregate đã biến đổi để tạo một collection báo cáo hoặc materialized view, có thể dùng stage ghi như `$merge` hoặc `$out` với quyền và chính sách phù hợp. Những stage này **khác** `$replaceRoot`/`$replaceWith`: chúng quyết định dữ liệu đầu ra được ghi ở đâu và theo quy tắc nào.

Tài liệu về `$merge`, `$out` và aggregation update nên được nghiên cứu trước khi thực hiện những thao tác có hiệu lực lưu trữ. Bài này tập trung vào cách biến đổi **root document** của pipeline.

## 16. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `$replaceWith: "$shipping"` khi field thiếu | Stage lỗi do không tạo document | `$match` kiểu object hoặc fallback an toàn |
| `$replaceWith` nhận `null`, string, number, array | Không phải root document hợp lệ | Kiểm tra `$type`, dựng object, hoặc dùng `$unwind` khi cần |
| Đưa mảng `items` trực tiếp lên root | Mảng không tự tách thành document | `$unwind` trước rồi thay root hoặc dựng object |
| Cho rằng `_id` tự giữ lại | Mất ID trong đầu ra | Thêm `_id: "$_id"` hoặc đổi tên `orderId` |
| Cho rằng các field khác được giữ | `status`, `runId`, `items` biến mất | Dựng object đích hoặc `$mergeObjects` |
| Dùng `$mergeObjects` nhưng không xét thứ tự operand | Field bị ghi đè ngoài ý muốn | Xác định field nào thắng khi trùng tên |
| Sử dụng `$$ROOT` rồi quên bỏ nested object | Dữ liệu bị lặp ở hai cấp | `$unset` field không muốn giữ |
| `$lookup` xong thay root bằng field mảng | Root không hợp lệ | `$unwind` hoặc lấy/chọn object hợp lệ |
| `$group` theo scalar rồi `$replaceWith:"$_id"` | Scalar không phải document | Bọc scalar trong object |
| `$match` theo field gốc sau khi đã đổi tên | Không lọc đúng dữ liệu | Lọc trước hoặc dùng tên field mới |
| Trả toàn bộ object customer sau lookup | Có thể lộ field không dành cho API | Dựng object tường minh/`$project` |
| Nghĩ `aggregate()` đã sửa collection | Dữ liệu lưu vẫn không đổi | Phân biệt stage biến đổi và stage/lệnh ghi |
| Dùng `$replaceWith` trong update mà bỏ `_id` | Update có thể lỗi hoặc gây mất field | Giữ `_id` và xác định các field cần bảo toàn |
| Không xem dữ liệu null/missing trước pipeline | Chỉ vài document xấu có thể làm cả phép aggregate thất bại | Schema validation, lọc kiểu hoặc fallback có chủ đích |

## 17. Bài thực hành tổng hợp

### 17.1. Bài A: trả địa chỉ giao hàng

Yêu cầu: tạo đầu ra có `orderNo`, `recipient`, `city` của mỗi order, kể cả order chưa có shipping. Gợi ý:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      recipient: {
        $ifNull: ["$shipping.recipient", "Chưa cung cấp"]
      },
      city: {
        $ifNull: ["$shipping.city", "Chưa xác định"]
      }
    }
  }
]);
```

Vì root mới được dựng thành một object tường minh nên không phụ thuộc `shipping` là object hay null để xác định **kiểu của root**. Tuy vậy, nếu dữ liệu shipping chứa kiểu bất thường, kết quả field path và fallback vẫn cần được xác định theo yêu cầu nghiệp vụ.

### 17.2. Bài B: mỗi dòng hàng một kết quả

Yêu cầu: tạo document đầu ra:

```javascript
{
  orderNo: "ORDER-186-01",
  sku: "BOOK-01",
  quantity: 2,
  unitPrice: 120000,
  lineAmount: 240000
}
```

Một pipeline:

```javascript
orders.aggregate([
  { $match: { runId } },
  { $unwind: "$items" },
  {
    $replaceWith: {
      orderNo: "$orderNo",
      sku: "$items.sku",
      quantity: "$items.quantity",
      unitPrice: "$items.unitPrice",
      lineAmount: {
        $multiply: [
          "$items.quantity",
          "$items.unitPrice"
        ]
      }
    }
  },
  { $sort: { orderNo: 1, sku: 1 } }
]);
```

Sự khác biệt với ví dụ trước: `$unwind` làm số document kết quả có thể **lớn hơn hoặc nhỏ hơn** số order đầu vào; `$replaceWith` chỉ định hình dạng của từng document đã được unwind.

### 17.3. Bài C: đưa key nhóm lên root

Yêu cầu: đếm đơn theo trạng thái, kết quả có `status` và `count` thay vì `_id` lồng nhau:

```javascript
orders.aggregate([
  { $match: { runId } },
  {
    $group: {
      _id: { status: "$status" },
      count: { $sum: 1 }
    }
  },
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          "$_id",
          { count: "$count" }
        ]
      }
    }
  },
  { $sort: { status: 1 } }
]);
```

### 17.4. Bài D: nhận diện pipeline có thể lỗi

Cho các biểu thức:

```javascript
// 1.
{ $replaceWith: "$shipping" }

// 2.
{ $replaceWith: { city: "$shipping.city" } }

// 3.
{ $replaceWith: "$items" }

// 4.
{ $replaceWith: { $ifNull: ["$shipping", {}] } }

// 5.
{ $replaceWith: {
    $cond: [
      { $eq: [{ $type: "$shipping" }, "object"] },
      "$shipping",
      {}
    ]
  }
}
```

Hãy phân tích:

1. Biểu thức nào có thể lỗi khi `shipping` thiếu hoặc null?
2. Biểu thức nào tạo object mới **bất kể shipping có null hay không**?
3. Nếu `shipping` là string, biểu thức số 4 có an toàn không?
4. Vì sao biểu thức số 3 không tự tách một mảng thành nhiều document?
5. Khi dùng biểu thức số 2, `_id` có được giữ tự động không?

Điểm cần nhớ: hãy kiểm tra **kiểu của biểu thức root cuối cùng**, không chỉ kiểu của một field con trong document mới.

## 18. Dọn dữ liệu thử nghiệm an toàn

Trước khi dọn, xác nhận database, collection, `runId` và các ID đã tạo trong phiên:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);

const ownedOrders = orders.find(
  { runId },
  { _id: 1, runId: 1, orderNo: 1 }
).toArray();

const ownedCustomers = customers.find(
  { runId },
  { _id: 1, runId: 1, displayName: 1 }
).toArray();

printjson(ownedOrders);
printjson(ownedCustomers);
```

Nếu danh sách đúng là dữ liệu bạn vừa tạo, xóa **chỉ những ID đó kèm `runId`**:

```javascript
for (const order of ownedOrders) {
  const result = orders.deleteOne({
    _id: order._id,
    runId
  });
  print("order deleted=" + result.deletedCount);
}

for (const customer of ownedCustomers) {
  const result = customers.deleteOne({
    _id: customer._id,
    runId
  });
  print("customer deleted=" + result.deletedCount);
}

print("remaining orders=" + orders.countDocuments({ runId }));
print("remaining customers=" + customers.countDocuments({ runId }));
```

Đừng dùng `deleteMany({})`, `drop()` hoặc `dropDatabase()` trong database có thể được người khác sử dụng. Nếu `runId` bị mất hoặc kết quả xem trước bất thường, dừng để xác nhận đúng dữ liệu sở hữu. Các ví dụ `aggregate()` thuần đọc ở bài này không tạo thêm document để phải dọn.

## 19. Câu hỏi ôn tập

1. Root document tại một stage aggregation là gì? `$$ROOT` có ý nghĩa như thế nào?
2. `$replaceRoot` và `$replaceWith` có khác nhau về mục đích hay chỉ khác cú pháp chính?
3. Vì sao `$replaceWith: "$shipping"` không hoạt động khi `shipping` là `null` hoặc missing?
4. `$ifNull` có bảo vệ khỏi `shipping` là string không? Nếu không, cần cơ chế gì?
5. Sau khi thay root bằng `shipping`, field `_id` và `status` đi đâu?
6. Làm sao giữ `orderId` của document gốc khi muốn lấy thông tin shipping làm root?
7. `$mergeObjects` xử lý hai object có cùng field theo thứ tự nào?
8. Vì sao `$replaceWith: "$items"` không thay thế được việc `$unwind` một mảng?
9. Sau `$lookup`, cần làm gì nếu field `customer` là mảng mà muốn đưa customer thành document gốc?
10. Vì sao group key dạng object có thể đưa lên root trực tiếp hơn group key dạng scalar?
11. Khi nào nên dùng `$project` thay vì `$replaceWith`?
12. Vì sao một `aggregate()` chỉ chứa `$replaceWith` không làm thay đổi document lưu, nhưng một `updateOne` với aggregation pipeline lại có thể làm thay đổi?
13. Nên đặt `$match` trước hay sau `$replaceWith` khi muốn tận dụng điều kiện lọc theo field gốc?
14. Nguy cơ nào xuất hiện khi merge toàn bộ object khách hàng vào document order mà không kiểm soát field được xuất?

## 20. Kết luận

`$replaceRoot` và `$replaceWith` là hai cách **thay toàn bộ root document đang đi qua aggregation pipeline**. Chúng hữu ích khi muốn nâng object lồng nhau lên cấp cao nhất, biến phần tử mảng thành document sau `$unwind`, đưa khóa `$group` lên root hoặc xây document kết quả từ dữ liệu `$lookup`.

Biểu thức thay root **phải trả về một document**, không được là `null`, missing, string, number hoặc array. Khi thay root, các field cũ — bao gồm `_id` — **không được tự giữ lại**; dùng `$mergeObjects` hoặc dựng object tường minh nếu cần bảo toàn dữ liệu. Cuối cùng, hãy nhớ phân biệt **thay hình dạng kết quả trong `aggregate()`** với **cập nhật dữ liệu thật trong update pipeline**: cùng một stage nhưng ngữ cảnh thực thi quyết định có ghi vào collection hay không.
