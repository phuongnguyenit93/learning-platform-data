# Cập nhật bằng aggregation pipeline và giới hạn các stage được phép trong MongoDB

Trong MongoDB, một lệnh cập nhật thông thường có thể tăng số lượng bằng `$inc`, đặt giá trị bằng `$set` hoặc xóa trường bằng `$unset`. Nhưng có những nghiệp vụ cần **tính giá trị mới từ dữ liệu đang lưu**: giá bán bằng đơn giá cộng phí giao hàng, trạng thái tồn kho phụ thuộc số lượng, chuẩn hóa tên, làm giàu các phần tử trong mảng hoặc chuyển đổi một cấu trúc document cũ.

**Cập nhật bằng aggregation pipeline** (aggregation pipeline updates) cho phép đặt **mảng các stage aggregation** vào đối số update, thay cho một document chứa update operators. MongoDB sẽ xử lý pipeline cho từng document khớp filter rồi ghi lại document kết quả, tuân theo các quy tắc cập nhật và validation của collection.

Điểm trọng tâm: **pipeline dùng để update không hỗ trợ mọi aggregation stage**. Chỉ một nhóm stage phục vụ biến đổi **từng document** được phép sử dụng.

Sau bài học, bạn sẽ biết cách dùng update pipeline, phân biệt hai loại `$set`/`$unset`, khai thác các biểu thức như `$add`, `$cond`, `$map`, `$filter`, `$ifNull`, nhận biết stage không hợp lệ và chọn phương án cập nhật phù hợp với ứng dụng thực tế.

## 1. Từ update operators sang update pipeline

Hai cách cập nhật cùng có thể tạo ra giá trị mới, nhưng **cú pháp và cách diễn giải** khác nhau.

### 1.1. Update truyền thống: đối số là object

Ví dụ tăng trường `stock` thêm 2:

~~~javascript
db.products.updateOne(
  { _id: "P-101" },
  { $inc: { stock: 2 } }
);
~~~

Object thứ hai chứa **update operator `$inc`**. Các toán tử cập nhật quen thuộc gồm `$set`, `$unset`, `$inc`, `$mul`, `$push`, `$pull`, `$addToSet` và nhiều toán tử khác.

### 1.2. Update pipeline: đối số là mảng

Cùng mục tiêu tăng `stock` thêm 2, nhưng biểu đạt bằng aggregation expression:

~~~javascript
db.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        stock: { $add: ["$stock", 2] }
      }
    }
  ]
);
~~~

Dấu hiệu nhận biết quan trọng là đối số thứ hai được đặt trong **ngoặc vuông `[...]`**:

~~~text
updateOne(filter, { updateOperator: ... })    -> update truyền thống
updateOne(filter, [ { stage: ... }, ... ])     -> update pipeline
~~~

Ở ví dụ pipeline:

- `$set` là **aggregation stage**.
- `$add` là **aggregation expression** bên trong stage `$set`.
- `"$stock"` tham chiếu **giá trị trường stock của document đang được cập nhật**.
- `2` là hằng số.
- Giá trị tính được ghi vào `stock`; các trường khác giữ nguyên.

Update pipeline được hỗ trợ từ **MongoDB 4.2**. Để chạy ví dụ, cần phiên bản server và driver/mongosh có hỗ trợ cú pháp mảng pipeline trong update.

### 1.3. Update pipeline không phải lệnh aggregate để chỉ đọc

So sánh:

~~~javascript
// Aggregate: tính kết quả và TRẢ VỀ cho client; không sửa document nguồn.
db.products.aggregate([
  { $set: { inventoryValue: { $multiply: ["$price", "$stock"] } } }
]);

// Pipeline update: tính kết quả rồi GHI các thay đổi vào document nguồn.
db.products.updateMany(
  {},
  [
    { $set: { inventoryValue: { $multiply: ["$price", "$stock"] } } }
  ]
);
~~~

Hai pipeline có thể dùng stage cùng tên, nhưng lệnh **`aggregate()`** tạo dòng kết quả, còn **`updateMany()`** tạo thay đổi bền vững trên các document được chọn.

Không nên xem pipeline update như “chạy aggregation bất kỳ rồi ghi lại”. MongoDB giới hạn chặt các stage được phép khi pipeline nằm trong lệnh update.

## 2. Các stage được phép: danh sách đầy đủ

Với update bằng aggregation pipeline, MongoDB chỉ hỗ trợ **sáu tên stage thuộc ba nhóm chức năng**:

| Stage | Tên tương đương | Tác dụng chính |
| --- | --- | --- |
| **`$set`** | `$addFields` | Thêm hoặc tính lại giá trị của các trường, giữ các trường còn lại |
| **`$addFields`** | `$set` | Tương tự `$set` |
| **`$unset`** | `$project` kiểu loại trừ | Loại bỏ một hoặc nhiều trường |
| **`$project`** | `$unset` nếu chỉ loại trừ | Chọn/loại/trình bày trường của document kết quả; phải cẩn trọng khi dùng làm update |
| **`$replaceRoot`** | `$replaceWith` | Thay toàn bộ document bằng object do biểu thức `newRoot` tạo ra |
| **`$replaceWith`** | `$replaceRoot` | Thay toàn bộ document bằng object kết quả của biểu thức |

Nhóm stage trên được cho phép trong `updateOne()`, `updateMany()` và các API hỗ trợ pipeline update như `findOneAndUpdate()`.

**Không được dùng những stage này bên trong update pipeline**:

| Stage không hợp lệ trong update pipeline | Vì sao không dùng tại đây? | Cách làm phù hợp |
| --- | --- | --- |
| `$match` | Lọc document thuộc **đối số filter** của lệnh update | `updateMany({ status: "active" }, [...])` |
| `$sort`, `$limit`, `$skip` | Đây là stage thay đổi tập document/luồng kết quả | Dùng filter và lựa chọn API phù hợp; truy vấn riêng để xác định document trước khi cập nhật |
| `$group`, `$count`, `$sortByCount` | Tổng hợp nhiều document, không còn biến đổi riêng từng document | Chạy `aggregate()` riêng để báo cáo/tính kết quả |
| `$lookup`, `$graphLookup`, `$unionWith` | Liên kết dữ liệu từ collection khác | Thiết kế luồng đọc/tính riêng và cập nhật sau theo nghiệp vụ |
| `$unwind` | Có thể tạo nhiều document đầu ra từ một document đầu vào | Dùng biểu thức mảng `$map`, `$filter` trong `$set` |
| `$out`, `$merge` | Là stage ghi kết quả aggregation vào collection | Sử dụng với `aggregate()` khi muốn materialize kết quả |
| `$facet`, `$bucket`, `$sample` | Thao tác luồng document hoặc nhiều nhánh xử lý | Tách khỏi pipeline update |

**Đừng nhầm stage với expression.** Ví dụ `$group` **không được** dùng như một stage trong update, nhưng biểu thức `$sum` để cộng các phần tử số của **một mảng trong cùng document** có thể xuất hiện bên trong `$set`. Tương tự, `$map` hoặc `$filter` là **biểu thức**, không phải stage của update pipeline.

Để lọc đối tượng cập nhật, viết điều kiện tại **filter**:

~~~javascript
// ĐÚNG: filter nằm ngoài mảng pipeline.
db.products.updateMany(
  { status: "active", stock: { $gt: 0 } },
  [
    { $set: { available: true } }
  ]
);

// SAI: $match không được phép là stage của update pipeline.
db.products.updateMany(
  {},
  [
    { $match: { status: "active" } },
    { $set: { available: true } }
  ]
);
~~~

Trong ví dụ thứ hai, MongoDB từ chối lệnh vì `$match` không nằm trong nhóm stage hợp lệ của update pipeline. Khi filter đúng, MongoDB chỉ đánh giá pipeline trên các document được chọn bởi filter đó.

## 3. Chuẩn bị dữ liệu trong mongosh

Sử dụng database riêng để có thể thử cập nhật mà không ảnh hưởng dữ liệu khác. Các giá tiền được tạo dưới dạng **Decimal128** để minh họa tính toán thập phân. Chạy trong `mongosh`:

~~~javascript
const lab = db.getSiblingDB("mongo_update_pipeline_lab");

lab.products.drop();

lab.products.insertMany([
  {
    _id: "P-101",
    sku: "MOUSE-01",
    name: "  Chuột không dây  ",
    category: "accessory",
    status: "active",
    price: Decimal128("150.00"),
    shippingFee: Decimal128("15.00"),
    stock: 5,
    tags: ["tech", "sale"],
    items: [
      { code: "USB", qty: 2, unitPrice: Decimal128("10.00") },
      { code: "PAD", qty: 1, unitPrice: Decimal128("25.00") }
    ],
    legacyCode: "OLD-M01"
  },
  {
    _id: "P-102",
    sku: "KEY-02",
    name: "Bàn phím cơ",
    category: "accessory",
    status: "draft",
    price: Decimal128("500.00"),
    shippingFee: Decimal128("30.00"),
    stock: 0,
    tags: ["office"],
    items: [
      { code: "KEYCAP", qty: 0, unitPrice: Decimal128("50.00") }
    ]
  },
  {
    _id: "P-103",
    sku: "BOOK-03",
    name: "MongoDB Guide",
    category: "book",
    status: "active",
    price: Decimal128("80.00"),
    shippingFee: Decimal128("10.00"),
    stock: 12,
    tags: ["learning"],
    items: []
  }
]);

lab.products.find().sort({ _id: 1 });
~~~

Trong các mục sau, mỗi ví dụ có thể **làm thay đổi dữ liệu thật của database lab**. Nếu muốn nhận lại kết quả từ trạng thái ban đầu, hãy chạy lại khối chuẩn bị dữ liệu sau khi đã chấp nhận xóa collection thực hành bằng `drop()`. Không chạy khối xóa dữ liệu này trên collection chứa thông tin cần giữ.

## 4. $set và $addFields: tính giá trị từ chính document

`$set` và `$addFields` là hai tên của cùng một **aggregation stage**. Stage giữ những trường đã có, đồng thời thêm trường mới hoặc **ghi đè giá trị trường cùng tên** bằng biểu thức tính toán.

### 4.1. Tính giá trị hàng tồn kho

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        inventoryValue: { $multiply: ["$price", "$stock"] },
        shippingIncluded: { $add: ["$price", "$shippingFee"] },
        updatedAt: "$$NOW"
      }
    }
  ]
);

lab.products.findOne(
  { _id: "P-101" },
  { sku: 1, inventoryValue: 1, shippingIncluded: 1, updatedAt: 1 }
);
~~~

Với `P-101` ban đầu:

- `inventoryValue = 150.00 × 5 = 750.00`.
- `shippingIncluded = 150.00 + 15.00 = 165.00`.
- `updatedAt` là ngày giờ máy chủ ghi nhận thông qua biến hệ thống `$$NOW`.

`$$NOW` có giá trị ngày giờ nhất quán trong suốt quá trình thực thi pipeline của lệnh. Biểu thức `"$price"` lấy giá trị từ document hiện tại, còn `Decimal128` giúp bảo toàn biểu diễn thập phân cho các phép toán được hỗ trợ trong giới hạn của Decimal128.

### 4.2. Tính điều kiện bằng $cond

Giả sử cần sinh trường `availability` từ `stock`:

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        availability: {
          $cond: [
            { $gt: ["$stock", 0] },
            "in_stock",
            "out_of_stock"
          ]
        }
      }
    }
  ]
);

lab.products.find(
  {},
  { _id: 1, stock: 1, availability: 1 }
).sort({ _id: 1 });
~~~

Kết quả logic:

| Sản phẩm | `stock` ban đầu | `availability` |
| --- | ---: | --- |
| P-101 | 5 | `in_stock` |
| P-102 | 0 | `out_of_stock` |
| P-103 | 12 | `in_stock` |

Có thể dùng `$switch` khi nhiều nhánh, ví dụ tồn kho bằng 0, tồn kho thấp và tồn kho đủ:

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        stockStatus: {
          $switch: {
            branches: [
              {
                case: { $lte: ["$stock", 0] },
                then: "out_of_stock"
              },
              {
                case: { $lt: ["$stock", 5] },
                then: "low_stock"
              }
            ],
            default: "in_stock"
          }
        }
      }
    }
  ]
);
~~~

Thứ tự nhánh `$switch` có ý nghĩa: MongoDB chọn nhánh đầu tiên có `case` đúng.

### 4.3. Chuẩn hóa một trường từ giá trị cũ

Tên của `P-101` có khoảng trắng ở hai đầu. Dùng `$trim` để cập nhật:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        name: { $trim: { input: "$name" } }
      }
    }
  ]
);

lab.products.findOne({ _id: "P-101" }, { name: 1 });
~~~

Tên lưu sau cập nhật là `"Chuột không dây"`. Trong update truyền thống, `{ $set: { name: "$name" } }` chỉ là giá trị được truyền cho update operator, không phải phép chuẩn hóa. Pipeline diễn giải `"$name"` là tham chiếu trường và cho phép lồng biểu thức như `$trim`.

### 4.4. $ifNull để đặt giá trị mặc định có điều kiện

Khi trường có thể bị thiếu hoặc `null`, có thể dùng `$ifNull`:

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        tags: { $ifNull: ["$tags", []] },
        shippingFee: {
          $ifNull: ["$shippingFee", Decimal128("0.00")]
        }
      }
    }
  ]
);
~~~

`$ifNull` trả giá trị thay thế khi biểu thức đầu vào là `null` hoặc không tồn tại. Đây là cách **backfill** các giá trị thiếu khi tất cả document được chọn cần mang kiểu chuẩn.

**Cẩn trọng:** `$ifNull` không sửa những trường có kiểu sai (ví dụ `tags` là chuỗi thay vì mảng). Khi có dữ liệu legacy không đồng nhất, cần kiểm tra kiểu với `$type` hoặc chuẩn hóa trước để tránh lỗi trong các biểu thức sau.

## 5. Stage chạy tuần tự: kết quả stage trước là đầu vào stage sau

Một pipeline update có thể chứa nhiều stage:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        normalizedName: { $trim: { input: "$name" } }
      }
    },
    {
      $set: {
        displayName: {
          $concat: ["$normalizedName", " (", "$sku", ")"]
        }
      }
    },
    {
      $unset: "normalizedName"
    }
  ]
);

lab.products.findOne(
  { _id: "P-101" },
  { name: 1, displayName: 1, normalizedName: 1 }
);
~~~

Kết quả có `displayName: "Chuột không dây (MOUSE-01)"`, nhưng không còn trường tạm `normalizedName`.

Các stage được chạy **theo thứ tự trong mảng**, nên stage thứ hai có thể đọc trường do stage thứ nhất tạo ra. Trong **cùng một `$set` stage**, không nên giả định các phép gán chạy lần lượt theo thứ tự khai báo rồi biểu thức sau được thấy ngay giá trị mới của biểu thức trước. Khi có phụ thuộc, hãy tách thành nhiều stage như ví dụ.

So sánh với update truyền thống: nó có các toán tử thay đổi trường, nhưng **không cho phép kết hợp một chuỗi stage biểu thức** theo cơ chế này.

## 6. $unset và $project: loại bỏ hay chọn trường

### 6.1. Stage $unset loại bỏ các trường chỉ định

Để xóa một trường cũ:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $unset: "legacyCode" }
  ]
);
~~~

Để xóa nhiều trường cùng lúc:

~~~javascript
lab.products.updateMany(
  {},
  [
    { $unset: ["obsoleteField", "temporaryNote"] }
  ]
);
~~~

Không có trường đó thì thao tác loại bỏ không cần tạo ra giá trị mới. Kết quả cập nhật vẫn tuân theo các ràng buộc khác của document.

Phân biệt rõ:

~~~javascript
// $unset là UPDATE OPERATOR: đối số update là object.
lab.products.updateOne(
  { _id: "P-101" },
  { $unset: { legacyCode: "" } }
);

// $unset là AGGREGATION STAGE: đối số update là mảng.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $unset: "legacyCode" }
  ]
);
~~~

Hai lệnh có thể cùng xóa một trường, nhưng **không được trộn cú pháp** của hai ngữ cảnh.

### 6.2. $project trong update có thể xóa hàng loạt field

Stage `$project` thường được dùng để chọn trường trong aggregation. Khi đặt vào **update pipeline**, document sau `$project` trở thành **document sẽ được ghi**. Vì vậy, các field không được giữ lại có thể bị xóa khỏi cơ sở dữ liệu.

Ví dụ một phép “chuyển document sang schema mới” có kiểm soát:

~~~javascript
// CHỈ DÙNG KHI MUỐN LOẠI BỎ MỌI FIELD KHÁC NGOÀI DANH SÁCH.
lab.products.updateOne(
  { _id: "P-103" },
  [
    {
      $project: {
        _id: 1,
        sku: 1,
        name: 1,
        category: 1,
        status: 1,
        price: 1,
        stock: 1,
        tags: 1
      }
    }
  ]
);
~~~

Sau phép cập nhật này, các field như `shippingFee`, `items` và field mới khác ngoài danh sách có thể biến mất khỏi `P-103`. Với ứng dụng thêm field liên tục, whitelist `$project` không đầy đủ có thể vô tình gây mất dữ liệu.

Nếu chỉ muốn xóa một vài field legacy, **ưu tiên `$unset`** thay cho `$project` bao gồm danh sách dài các trường được giữ.

### 6.3. Không xóa hoặc thay đổi _id

Trường `_id` là định danh bất biến của document. Update pipeline không được biến một document đang tồn tại thành document có `_id` khác hoặc thiếu `_id`. Cẩn trọng với `$project`, `$replaceWith` và `$replaceRoot`: dù stage aggregate thông thường có thể tạo một hình dạng kết quả khác, **ghi kết quả đó bằng update vẫn phải tôn trọng quy tắc _id**.

Ví dụ cần tránh:

~~~javascript
// Không hợp lệ khi update một document đã có _id.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $set: { _id: "P-999" } }
  ]
);
~~~

Thao tác bị từ chối vì cố đổi định danh của document đang lưu. Các giới hạn khác như schema validation và shard key (khi collection sharded) cũng tiếp tục áp dụng theo cấu hình triển khai.

## 7. $replaceRoot và $replaceWith: xây dựng lại document

Hai stage này cho phép thay **toàn bộ object gốc** bằng một document mới được tính từ biểu thức.

Cú pháp:

~~~javascript
// $replaceRoot nhận object chứa newRoot.
{ $replaceRoot: { newRoot: <documentExpression> } }

// $replaceWith nhận trực tiếp expression tạo document.
{ $replaceWith: <documentExpression> }
~~~

Trong update pipeline, hai stage gần như tương đương về khả năng thay đổi cấu trúc document. Vì kết quả sẽ được ghi lại, hãy **giữ nguyên _id** và những trường nghiệp vụ phải tồn tại.

### 7.1. Dùng $replaceWith kết hợp $mergeObjects

Giả sử muốn bổ sung object `audit` cho sản phẩm, nhưng giữ nguyên các trường khác:

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $replaceWith: {
        $mergeObjects: [
          "$$ROOT",
          {
            audit: {
              source: "pipeline-lab",
              changedAt: "$$NOW"
            }
          }
        ]
      }
    }
  ]
);

lab.products.findOne(
  { _id: "P-102" },
  { _id: 1, sku: 1, audit: 1 }
);
~~~

Ở đây:

- `$$ROOT` là document hiện tại.
- `$mergeObjects` gộp các object theo thứ tự; giá trị ở object sau ghi đè trường cùng tên ở object trước.
- `_id` nằm trong `$$ROOT` nên được giữ nguyên.
- `audit` mới thay thế một `audit` cũ nếu có.

Nếu muốn **giữ các trường con cũ trong audit**, cần merge cả object `audit` thay vì ghi đè toàn bộ:

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $replaceWith: {
        $mergeObjects: [
          "$$ROOT",
          {
            audit: {
              $mergeObjects: [
                { source: "unknown" },
                "$audit",
                { changedAt: "$$NOW" }
              ]
            }
          }
        ]
      }
    }
  ]
);
~~~

Trường `source` cũ trong `audit` (nếu có) sẽ được giữ do object `"$audit"` xuất hiện sau giá trị mặc định; `changedAt` được cập nhật. Với trường `audit` hoàn toàn thiếu, `$mergeObjects` có thể bỏ qua giá trị null/missing của toán hạng và dùng object mặc định.

### 7.2. Cú pháp $replaceRoot tương đương

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $replaceRoot: {
        newRoot: {
          $mergeObjects: [
            "$$ROOT",
            { reviewFlag: true }
          ]
        }
      }
    }
  ]
);
~~~

Kết quả giữ nguyên dữ liệu hiện tại và bổ sung `reviewFlag`. Với những cập nhật chỉ thêm hoặc sửa một vài trường, `$set` thường đơn giản hơn. `$replaceRoot`/`$replaceWith` phù hợp hơn khi cần đổi cấu trúc phức tạp, nhưng cũng dễ vô tình làm mất field nếu không giữ `$$ROOT` hoặc không liệt kê đầy đủ các thuộc tính cần thiết.

### 7.3. Điều kiện bắt buộc đối với replacement

Biểu thức của `$replaceWith` phải trả về **document/object**, không phải chuỗi, số hay mảng. Ví dụ trả về giá trị `"$name"` (một chuỗi) không phải replacement document hợp lệ.

Ngoài `_id` bất biến, kết quả còn phải hợp lệ theo **schema validation** của collection, giới hạn kích thước document BSON và những ràng buộc triển khai liên quan. Vì vậy hãy thử trên dữ liệu mẫu trước khi chạy thao tác rộng.

## 8. Biểu thức aggregation sử dụng được bên trong stage cập nhật

Stage hợp lệ chỉ là **vỏ bọc của pipeline**. Bên trong stage như `$set`, MongoDB cho phép nhiều **aggregation expression** để tính giá trị trường.

| Nhu cầu | Biểu thức thường dùng | Ví dụ mục tiêu |
| --- | --- | --- |
| Cộng/trừ/nhân/chia | `$add`, `$subtract`, `$multiply`, `$divide` | Tính tổng, trừ tồn kho, nhân giá |
| So sánh/logic | `$eq`, `$gt`, `$lt`, `$and`, `$or` | Tính cờ trạng thái |
| Điều kiện | `$cond`, `$switch` | Chọn nhánh dựa trên dữ liệu hiện tại |
| Dữ liệu thiếu | `$ifNull`, `$type` | Đặt mặc định, kiểm tra kiểu |
| Chuỗi | `$concat`, `$trim`, `$toUpper`, `$toLower` | Chuẩn hóa tên và mã |
| Ngày giờ | `$$NOW`, `$dateAdd`, `$dateDiff` | Cập nhật timestamp hoặc hạn xử lý |
| Mảng | `$map`, `$filter`, `$concatArrays`, `$setUnion`, `$size` | Biến đổi và bổ sung phần tử |
| Object | `$mergeObjects`, `$getField`, `$setField` | Hợp nhất/đọc/ghi field |
| Chuyển kiểu | `$toInt`, `$toDecimal`, `$convert` | Chuẩn hóa dữ liệu legacy |

**Đừng nhầm toán tử cùng tên ở hai vai trò.** Ví dụ `$and` trong filter là **query operator**; trong biểu thức `$cond`, `$and` là **aggregation expression** nhận mảng biểu thức logic. `$set` ở stage pipeline cũng khác update operator `$set` nằm ngoài pipeline.

### 8.1. Cộng số dựa trên giá trị trường hiện tại

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        stock: { $add: ["$stock", 3] }
      }
    }
  ]
);
~~~

Nếu stock ban đầu là 5, sau lệnh sẽ là 8. Chạy lại lệnh sẽ tiếp tục tăng thêm 3, vì biểu thức đọc giá trị hiện tại của document. Đây là một thao tác **không idempotent**; cần quản lý retry theo ngữ nghĩa nghiệp vụ.

### 8.2. Làm tròn tiền và giữ đúng kiểu thập phân

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        priceWithTax: {
          $round: [
            {
              $multiply: [
                "$price",
                Decimal128("1.08")
              ]
            },
            2
          ]
        }
      }
    }
  ]
);
~~~

Với giá 150.00 và hệ số 1.08, kết quả là **162.00**. Việc truyền hệ số bằng `Decimal128("1.08")` giúp tính toán thập phân trong giới hạn của Decimal128. Ứng dụng vẫn cần định nghĩa quy tắc làm tròn và số chữ số thập phân theo yêu cầu tài chính thực tế.

### 8.3. Bảo vệ giá trị literal bắt đầu bằng $

Trong aggregation expression, chuỗi bắt đầu bằng `$` được hiểu là **tham chiếu field** hoặc biến hệ thống. Muốn lưu chính chuỗi `"$VIP-2026"`, dùng `$literal`:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        campaignCode: { $literal: "$VIP-2026" }
      }
    }
  ]
);
~~~

Nếu viết `campaignCode: "$VIP-2026"`, MongoDB sẽ cố diễn giải thành đường dẫn field, không phải chuỗi literal mong muốn. Đây là trường hợp đặc biệt quan trọng khi giá trị được xây dựng từ input người dùng hoặc nguồn ngoài.

### 8.4. Dùng $convert khi dữ liệu legacy khác kiểu

Giả sử một collection cũ chứa `stock` dạng chuỗi, ta có thể chuyển sang số nguyên:

~~~javascript
// Minh họa độc lập cho document legacy có stock = "12".
db.legacy_products.updateMany(
  { stock: { $type: "string" } },
  [
    {
      $set: {
        stock: {
          $convert: {
            input: "$stock",
            to: "int",
            onError: 0,
            onNull: 0
          }
        }
      }
    }
  ]
);
~~~

Đây là ví dụ cho một collection `legacy_products` giả định; nó không được tạo trong bộ dữ liệu `lab.products`. Cần cân nhắc kỹ việc đặt `onError: 0`: giá trị sai định dạng có thể bị biến thành số 0 và che giấu dữ liệu bẩn. Trong sản phẩm thực, thường nên **ghi nhận bản ghi lỗi để xử lý** trước khi quyết định giá trị thay thế.

## 9. Cập nhật mảng bằng $map, $filter và $concatArrays

Aggregation pipeline update không nhận `arrayFilters` kiểu update truyền thống. Khi cần xử lý phần tử mảng bằng pipeline, hãy dùng **biểu thức mảng** trong một stage hợp lệ.

### 9.1. Tính giá trị cho từng phần tử bằng $map

Sản phẩm `P-101` có mảng `items` gồm các object `{code, qty, unitPrice}`. Muốn thêm `lineTotal = qty × unitPrice` vào **từng** phần tử:

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        items: {
          $map: {
            input: { $ifNull: ["$items", []] },
            as: "item",
            in: {
              $mergeObjects: [
                "$$item",
                {
                  lineTotal: {
                    $multiply: [
                      "$$item.qty",
                      "$$item.unitPrice"
                    ]
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
);
~~~

Phần tử đầu trở thành:

~~~javascript
{
  code: "USB",
  qty: 2,
  unitPrice: Decimal128("10.00"),
  lineTotal: Decimal128("20.00")
}
~~~

`$map` tạo mảng mới có các phần tử kết quả, còn `$mergeObjects` giữ trường ban đầu và bổ sung `lineTotal`. Nếu trường `items` bị thiếu hoặc null, `$ifNull` tạo mảng rỗng để tránh lỗi đầu vào. Nếu `items` tồn tại nhưng mang kiểu string, vẫn cần chuẩn hóa/kiểm tra kiểu trước.

### 9.2. Bỏ phần tử không hợp lệ bằng $filter

Với `P-102`, `items` chứa một phần tử có `qty: 0`. Muốn giữ những phần tử có số lượng lớn hơn 0:

~~~javascript
lab.products.updateOne(
  { _id: "P-102" },
  [
    {
      $set: {
        items: {
          $filter: {
            input: { $ifNull: ["$items", []] },
            as: "item",
            cond: { $gt: ["$$item.qty", 0] }
          }
        }
      }
    }
  ]
);

lab.products.findOne({ _id: "P-102" }, { items: 1 });
~~~

Kết quả `items` của `P-102` là `[]`. `$filter` **giữ các phần tử thỏa điều kiện**, còn các phần tử khác không xuất hiện trong mảng được ghi lại.

### 9.3. Thêm phần tử bằng $concatArrays

Để thêm một tag mới vào cuối mảng:

~~~javascript
lab.products.updateOne(
  { _id: "P-103" },
  [
    {
      $set: {
        tags: {
          $concatArrays: [
            { $ifNull: ["$tags", []] },
            ["featured"]
          ]
        }
      }
    }
  ]
);
~~~

`$concatArrays` nối các mảng theo thứ tự; nếu chạy lệnh nhiều lần, `"featured"` sẽ bị thêm nhiều lần. Nếu cần **không trùng phần tử**, dùng `$setUnion`:

~~~javascript
lab.products.updateOne(
  { _id: "P-103" },
  [
    {
      $set: {
        tags: {
          $setUnion: [
            { $ifNull: ["$tags", []] },
            ["featured"]
          ]
        }
      }
    }
  ]
);
~~~

`$setUnion` trả về tập hợp giá trị không trùng, nhưng **không bảo đảm giữ nguyên thứ tự** của mảng. Chọn công cụ theo nghiệp vụ: lịch sử có thứ tự khác danh sách tag duy nhất.

### 9.4. Vì sao không dùng $[identifier] với arrayFilters?

Cú pháp thông thường cho cập nhật phần tử mảng là:

~~~javascript
// Đây là UPDATE TRUYỀN THỐNG, không phải aggregation pipeline.
db.orders.updateMany(
  {},
  { $set: { "items.$[item].reviewed": true } },
  { arrayFilters: [{ "item.qty": { $gt: 0 } }] }
);
~~~

Nhưng `arrayFilters` **không dùng được** trong thao tác cập nhật có đối số thứ hai là **aggregation pipeline**. Với pipeline, mô tả phép biến đổi mảng bằng `$map`, `$filter` hoặc biểu thức phù hợp, thay vì gắn `arrayFilters` vào update pipeline.

Hai cơ chế có ưu điểm khác nhau:

- **Update operator + arrayFilters:** thuận tiện khi thay đổi một vài field của các phần tử thỏa điều kiện.
- **Pipeline + $map/$filter:** thuận tiện khi cần tính toán, chuyển đổi cấu trúc hoặc ghép nhiều biểu thức trên mỗi phần tử.

Không nên chuyển sang pipeline chỉ để “trông hiện đại hơn” nếu một update operator đơn giản đã diễn tả đúng nghiệp vụ.

## 10. Lọc bằng filter và viết pipeline sao cho an toàn

### 10.1. Update filter là điều kiện chọn document

Bài toán: giảm 2 đơn vị tồn kho **chỉ khi còn ít nhất 2**. Dùng điều kiện ngay ở filter:

~~~javascript
const result = lab.products.updateOne(
  {
    _id: "P-101",
    stock: { $gte: 2 }
  },
  [
    {
      $set: {
        stock: { $subtract: ["$stock", 2] },
        updatedAt: "$$NOW"
      }
    }
  ]
);

printjson(result);
~~~

Filter và update trên cùng một document được thực hiện nguyên tử ở phạm vi **document đó**. Nếu stock không đủ ở thời điểm thao tác được áp dụng, filter sẽ không khớp và không có cập nhật. Theo dõi `matchedCount` để phân biệt trường hợp đủ điều kiện và không đủ điều kiện.

Không nên chỉ làm:

~~~javascript
// Dễ đưa stock thành số âm nếu không có ràng buộc ở filter.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $set: { stock: { $subtract: ["$stock", 2] } } }
  ]
);
~~~

Một schema validator có thể ngăn stock âm, nhưng kiểm tra điều kiện ngay trong filter thường diễn đạt rõ **quy tắc nghiệp vụ của một thao tác trừ tồn kho** hơn.

### 10.2. Tránh thay đổi toàn bộ collection do filter rộng

`updateMany({}, pipeline)` chọn tất cả document trong collection. Cần đặc biệt cẩn trọng nếu stage dùng `$project`, `$unset` hoặc `$replaceWith` vì có thể xóa field trên toàn bộ dữ liệu.

Trước một cập nhật lớn, nên đọc filter:

~~~javascript
const targetFilter = {
  status: "draft",
  category: "accessory"
};

lab.products.find(
  targetFilter,
  { _id: 1, sku: 1, status: 1, category: 1 }
);

lab.products.countDocuments(targetFilter);
~~~

Sau khi đã xác định đúng phạm vi, mới áp dụng pipeline:

~~~javascript
lab.products.updateMany(
  targetFilter,
  [
    {
      $set: {
        needsReview: true,
        reviewedAt: "$$NOW"
      }
    }
  ]
);
~~~

Kiểm tra phạm vi trước khi ghi đặc biệt hữu ích, nhưng trong môi trường nhiều client đồng thời, dữ liệu có thể thay đổi giữa hai lệnh đọc và ghi. Không được coi lệnh `find()` trước đó là cơ chế khóa hay transaction.

### 10.3. updateOne và updateMany khác nhau ở độ nguyên tử

- `updateOne` cập nhật tối đa một document khớp filter.
- `updateMany` có thể cập nhật nhiều document, nhưng **không biến toàn bộ lệnh thành một transaction nguyên tử trên nhiều document**.
- Mỗi thay đổi lên một document có tính nguyên tử ở cấp document. Nếu yêu cầu nhiều document phải thành công hoặc thất bại cùng nhau, cần cân nhắc **multi-document transaction** trên deployment hỗ trợ, cùng chiến lược retry phù hợp.

Khi pipeline phức tạp hoặc mảng lớn, thời gian xử lý mỗi document cũng có thể tăng. Không thể dùng `$group` bên trong update pipeline để biến nó thành giao dịch tính gộp toàn collection.

## 11. Upsert với update pipeline

`upsert: true` có nghĩa: nếu không có document khớp filter, MongoDB có thể **tạo document mới** rồi áp dụng pipeline.

Ví dụ tạo sản phẩm mới nếu chưa tồn tại:

~~~javascript
lab.products.updateOne(
  { _id: "P-NEW" },
  [
    {
      $set: {
        sku: "NEW-001",
        name: "Sản phẩm mới",
        category: "accessory",
        status: "draft",
        stock: 0,
        price: Decimal128("0.00"),
        tags: [],
        createdAt: "$$NOW",
        updatedAt: "$$NOW"
      }
    }
  ],
  { upsert: true }
);
~~~

Với filter bằng `_id` như trên, document mới mang định danh `"P-NEW"`. Nếu chạy lại, lệnh sẽ **cập nhật** document đã tồn tại thay vì chèn thêm một document khác.

**Cẩn trọng:** trong ví dụ trên, chạy lại sẽ ghi lại `createdAt` vì pipeline đặt trường đó không điều kiện. Nếu `createdAt` chỉ được ghi khi tạo mới, có thể dùng `$ifNull` để giữ giá trị cũ:

~~~javascript
lab.products.updateOne(
  { _id: "P-NEW" },
  [
    {
      $set: {
        sku: "NEW-001",
        createdAt: { $ifNull: ["$createdAt", "$$NOW"] },
        updatedAt: "$$NOW"
      }
    }
  ],
  { upsert: true }
);
~~~

Nên dùng filter có khóa duy nhất, thường là `_id` hoặc trường đã được tạo **unique index**, để giảm nguy cơ hai thao tác upsert đồng thời tạo dữ liệu trùng logic.

Nếu pipeline tính toán dựa trên một field chỉ tồn tại ở document cũ, cần xác định rõ giá trị mặc định khi upsert tạo document mới. Ví dụ `{$add: ["$stock", 1]}` không tự an toàn khi `stock` thiếu; nên dùng `{$add: [{$ifNull: ["$stock", 0]}, 1]}` trong trường hợp đó.

## 12. Phân biệt biểu thức trong pipeline với update operators

Đây là nguồn nhầm lẫn thường gặp khi bắt đầu dùng aggregation pipeline updates.

| Mục đích | Update operators truyền thống | Update pipeline dùng stage/expression |
| --- | --- | --- |
| Gán trường một hằng | `{ $set: { status: "active" } }` | `[ { $set: { status: "active" } } ]` |
| Tăng stock thêm 2 | `{ $inc: { stock: 2 } }` | `[ { $set: { stock: { $add: ["$stock", 2] } } } ]` |
| Xóa field legacy | `{ $unset: { legacy: "" } }` | `[ { $unset: "legacy" } ]` |
| Thêm phần tử vào mảng | `{ $push: { tags: "new" } }` | `[ { $set: { tags: { $concatArrays: ["$tags", ["new"]] } } } ]` |
| Chỉ giữ phần tử mảng thỏa điều kiện | `$pull` để loại phần tử theo điều kiện | `$filter` trong `$set` để tạo mảng mới |
| Cập nhật phần tử bằng arrayFilters | Có với `$[identifier]` và options | Không hỗ trợ `arrayFilters`; dùng `$map` |
| Tính giá trị từ field khác | Cần giải pháp phù hợp, thường nhiều bước hoặc logic ứng dụng | `$set` stage với `$add`/`$multiply`/`$concat`/`$cond` |

Không thể đưa update operator `$inc` làm một stage trong pipeline:

~~~javascript
// SAI: $inc không phải aggregation stage được phép trong update pipeline.
lab.products.updateOne(
  { _id: "P-101" },
  [
    { $inc: { stock: 1 } }
  ]
);

// ĐÚNG: tính lại stock bằng aggregation expression.
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        stock: { $add: ["$stock", 1] }
      }
    }
  ]
);
~~~

Cũng không nên nhầm **`$set` stage** với **`$set` update operator**:

~~~javascript
// Update operator: biến string "$name" là GIÁ TRỊ được gán theo
// ngữ nghĩa của update truyền thống.
{ $set: { displayName: "$name" } }

// Aggregation stage: "$name" là THAM CHIẾU đến field name hiện tại.
[ { $set: { displayName: "$name" } } ]
~~~

Chỉ cần nhìn dấu ngoặc **`{...}` so với `[{...}]`** ở đối số update là biết MongoDB sẽ dùng kiểu diễn giải nào.

## 13. Lưu ý về schema, kiểu dữ liệu và hiệu năng

### 13.1. Validation vẫn áp dụng sau khi cập nhật

Nếu collection có JSON Schema validator, kết quả của update pipeline vẫn phải tuân thủ các ràng buộc như:

- Trường bắt buộc (`required`).
- Kiểu BSON (`bsonType`).
- Giá trị trong danh sách (`enum`).
- Giới hạn số (`minimum`/`maximum`).
- Quy tắc chuỗi (`minLength`/`pattern`).

Ví dụ `$project` vô tình xóa field bắt buộc có thể khiến update bị từ chối khi collection dùng `validationLevel: "strict"` và `validationAction: "error"`. Validator không tự sửa pipeline.

### 13.2. Thao tác tính toán có thể lỗi khi field thiếu hoặc khác kiểu

Giả sử `stock` đôi lúc là chuỗi `"5"` thay vì số. Biểu thức:

~~~javascript
{ $add: ["$stock", 1] }
~~~

có thể gây lỗi vì toán hạng không đúng kiểu. Đừng mặc định pipeline update tự ép mọi dữ liệu về số.

Có thể dùng `$convert`, `$toInt` hoặc `$ifNull` để xử lý tình huống cụ thể, nhưng cần thống nhất chính sách đối với dữ liệu đầu vào lỗi. Tránh âm thầm thay dữ liệu xấu thành 0 nếu điều đó làm sai lệch tồn kho hay số tiền.

### 13.3. Không tạo _id mới và không vượt các giới hạn document

- `_id` của document đã có không thể bị đổi bằng `$set` hay replacement stage.
- Document kết quả phải tuân thủ kích thước BSON tối đa và các giới hạn hệ thống.
- Trên collection sharded, thay đổi shard key có các điều kiện riêng; pipeline update không làm mất những quy tắc đó.
- Quyền ghi, write concern và transaction semantics vẫn áp dụng.

### 13.4. Tác động tới index và chi phí xử lý

Index chủ yếu giúp MongoDB **tìm đúng document** theo filter:

~~~javascript
lab.products.createIndex({
  status: 1,
  category: 1
});
~~~

Nếu thường chạy:

~~~javascript
lab.products.updateMany(
  { status: "active", category: "accessory" },
  [
    {
      $set: {
        inventoryValue: { $multiply: ["$price", "$stock"] }
      }
    }
  ]
);
~~~

thì compound index trên `status` và `category` có thể giúp lựa chọn document, tùy dữ liệu và query planner. Sau khi tìm được document, biểu thức `$multiply` vẫn được thực thi riêng trên các document khớp. Cập nhật field đã được index còn có thể làm tăng chi phí duy trì index.

Nếu pipeline có `$map` qua một mảng rất lớn, chi phí sẽ tăng theo số phần tử được xử lý. MongoDB update pipeline **không tự lưu kết quả biến đổi của mảng ở nơi khác**: nó ghi lại giá trị mới vào document phù hợp với mô hình cập nhật.

### 13.5. Idempotency và retry

Một pipeline như:

~~~javascript
[
  { $set: { normalizedName: { $trim: { input: "$name" } } } }
]
~~~

thường mang tính **idempotent**: chạy lại trên cùng dữ liệu không tiếp tục đổi tên đã chuẩn hóa.

Ngược lại:

~~~javascript
[
  { $set: { stock: { $add: ["$stock", 1] } } }
]
~~~

sẽ tăng thêm 1 mỗi lần thực thi. Với thao tác mạng bị timeout, ứng dụng cần phân biệt driver retryable writes và việc tự gửi lại lệnh cấp nghiệp vụ. **Không tự lặp một update có tác dụng tăng/trừ** nếu chưa xác định thao tác trước đã được áp dụng hay chưa. Với nghiệp vụ tài chính hoặc tồn kho, thường cần khóa/idempotency key hoặc một chiến lược cập nhật an toàn hơn.

## 14. Lỗi thường gặp và hướng xử lý

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Stage `$match`, `$group` hoặc `$lookup` bị báo không hợp lệ | Update pipeline chỉ nhận sáu tên stage | Đưa lọc vào filter; tách tổng hợp nhiều document ra `aggregate()` riêng |
| Stage `$inc`/`$push` bị từ chối | Đây là update operator, không phải aggregation stage | Dùng update truyền thống hoặc viết biểu thức `$add`/`$concatArrays` trong `$set` |
| Dữ liệu lưu thành chuỗi `"$price"` ngoài ý định | Nhầm ngữ nghĩa update truyền thống và pipeline | Dùng pipeline khi cần tham chiếu trường hiện tại |
| Chuỗi `"$VIP"` bị coi là field path | Giá trị literal bắt đầu bằng `$` | Bọc bằng `{$literal: "$VIP"}` |
| `$add` báo lỗi với field thiếu/chuỗi | Toán hạng không đúng kiểu | Kiểm tra BSON type, `$ifNull`, `$convert` |
| `$project` khiến mất nhiều field | Stage chỉ giữ những field được liệt kê | Dùng `$unset` nếu chỉ xóa vài field |
| `$replaceWith` báo lỗi | Expression không tạo object hoặc vi phạm ràng buộc update | Đảm bảo object hợp lệ, giữ `_id` và trường bắt buộc |
| Không dùng được `arrayFilters` với pipeline | Hai cú pháp cập nhật không hỗ trợ kết hợp | Chọn update operator + arrayFilters hoặc pipeline + `$map` |
| Cập nhật mảng có phần tử trùng | `$concatArrays` nối phần tử mỗi lần chạy | Dùng `$setUnion` nếu cần unique, lưu ý thứ tự |
| Upsert làm mất ý nghĩa `createdAt` | Mỗi lần cập nhật lại gán `$$NOW` | Dùng `$ifNull` hoặc chiến lược chỉ-ghi-khi-tạo |
| `matchedCount = 0` | Không có document thỏa filter tại thời điểm update | Kiểm tra điều kiện, kiểu dữ liệu và trạng thái hiện tại |
| `modifiedCount = 0` nhưng matchedCount > 0 | Document khớp nhưng kết quả không tạo thay đổi thực tế | Kiểm tra giá trị trước/sau và logic pipeline |
| UpdateMany cập nhật được một phần khi lỗi | Không có atomicity toàn bộ đa document | Thiết kế transaction hoặc cơ chế phục hồi khi cần |
| Lệnh chậm | Filter kém index, xử lý biểu thức/mảng phức tạp, nhiều document | Tối ưu filter/index, giới hạn phạm vi, quan sát profiler/metrics |

Không nên sửa cả pipeline một cách cảm tính khi nhận lỗi. Hãy xác định trước **đối số update là object hay array**, **stage có thuộc danh sách được phép không**, **biểu thức có đọc đúng field/BSON type không**, và **document kết quả có vi phạm validation không**.

## 15. Bài thực hành và kết quả mong đợi

Các bài dưới đây giả định bạn đã khởi tạo lại `lab.products` từ mục 3 nếu từng chạy các cập nhật trước. Hãy tự viết và đọc lại document sau mỗi lệnh.

### Bài 1 — Tính trường mới

Tạo `totalPrice` bằng `price + shippingFee` cho mọi sản phẩm.

~~~javascript
lab.products.updateMany(
  {},
  [
    {
      $set: {
        totalPrice: { $add: ["$price", "$shippingFee"] }
      }
    }
  ]
);
~~~

Kết quả dự kiến từ dữ liệu gốc:

| `_id` | Giá | Phí giao | `totalPrice` |
| --- | ---: | ---: | ---: |
| P-101 | 150.00 | 15.00 | 165.00 |
| P-102 | 500.00 | 30.00 | 530.00 |
| P-103 | 80.00 | 10.00 | 90.00 |

### Bài 2 — Thêm và xóa trường tạm

Tạo `temporaryLabel` từ `sku`, rồi đổi thành `displayCode` ở stage tiếp theo và xóa trường tạm.

~~~javascript
lab.products.updateOne(
  { _id: "P-101" },
  [
    {
      $set: {
        temporaryLabel: { $concat: ["CODE-", "$sku"] }
      }
    },
    {
      $set: {
        displayCode: "$temporaryLabel"
      }
    },
    {
      $unset: "temporaryLabel"
    }
  ]
);
~~~

Kết quả `displayCode` là `"CODE-MOUSE-01"`, còn `temporaryLabel` không tồn tại.

### Bài 3 — Cập nhật có điều kiện

Chỉ áp dụng lệnh cho sản phẩm đang `active`, tính `canSell` bằng điều kiện `stock > 0`:

~~~javascript
lab.products.updateMany(
  { status: "active" },
  [
    {
      $set: {
        canSell: { $gt: ["$stock", 0] }
      }
    }
  ]
);
~~~

Từ dữ liệu gốc, `P-101` và `P-103` có `canSell: true`. `P-102` không bị thay đổi vì trạng thái `draft`.

### Bài 4 — Biến đổi phần tử trong mảng

Thêm field `lineTotal` cho mọi item bằng `$map` và `$multiply`, giữ nguyên các field cũ của mỗi item. Thử chạy với `P-101` và so sánh hai phần tử:

- `USB` có `qty: 2`, `unitPrice: 10.00` nên `lineTotal: 20.00`.
- `PAD` có `qty: 1`, `unitPrice: 25.00` nên `lineTotal: 25.00`.

Gợi ý xem lại mục 9.1 về `$map` cùng `$mergeObjects`.

### Bài 5 — Tìm stage không hợp lệ

Xem đoạn sau:

~~~javascript
lab.products.updateMany(
  {},
  [
    { $match: { stock: { $gt: 0 } } },
    { $set: { available: true } },
    { $sort: { stock: -1 } }
  ]
);
~~~

Hãy viết lại để **chỉ cập nhật sản phẩm stock > 0**, không sử dụng `$match` và `$sort` ở vị trí stage update. Một lời giải:

~~~javascript
lab.products.updateMany(
  { stock: { $gt: 0 } },
  [
    { $set: { available: true } }
  ]
);
~~~

Thứ tự sort không ảnh hưởng ý nghĩa cập nhật hàng loạt trong bài toán này.

### Bài 6 — Chọn giữa update truyền thống và pipeline

Với mỗi yêu cầu, chọn cách ngắn gọn và đúng nhất:

1. Chỉ tăng `stock` thêm 1.
2. Tính `inventoryValue` bằng `price × stock`.
3. Gỡ một tag cụ thể khỏi mảng.
4. Chuẩn hóa `name` bằng `$trim`.
5. Chuyển từng phần tử `items` thành object có thêm `lineTotal`.
6. Đổi một field bình thường thành hằng `"active"`.

Gợi ý: (1), (3), (6) thường có update operators truyền thống phù hợp; (2), (4), (5) là các tình huống pipeline thể hiện lợi ích rõ rệt. Riêng với (3), nếu yêu cầu loại phần tử theo biểu thức phức tạp, `$filter` cũng có thể là lựa chọn.

### Bài 7 — Phân biệt update pipeline với aggregation đọc

So sánh hai lệnh:

~~~javascript
// Lệnh A
lab.products.aggregate([
  { $group: { _id: "$category", totalStock: { $sum: "$stock" } } }
]);

// Lệnh B (không hợp lệ)
lab.products.updateMany(
  {},
  [
    { $group: { _id: "$category", totalStock: { $sum: "$stock" } } }
  ]
);
~~~

Giải thích vì sao lệnh A chạy được dưới dạng aggregation, còn lệnh B không được MongoDB cho phép trong update pipeline. Nếu mục tiêu là lưu báo cáo tổng tồn kho theo category, cần một luồng aggregate/materialize riêng, không phải một lệnh `updateMany()` dùng `$group`.

## 16. Tóm lược các nguyên tắc quan trọng

**Aggregation pipeline update** cho phép tính toán giá trị cập nhật dựa trên document hiện tại và chạy nhiều stage biến đổi theo thứ tự. Nó đặc biệt hiệu quả khi cần cập nhật có điều kiện, chuẩn hóa field, biến đổi mảng hay đổi cấu trúc tài liệu.

Những nguyên tắc cần giữ:

1. Đối số update là **mảng `[...]`** thì MongoDB hiểu đây là **pipeline**.
2. Chỉ sáu tên stage được phép: **`$set`, `$addFields`, `$unset`, `$project`, `$replaceRoot`, `$replaceWith`**.
3. Các biểu thức như **`$add`, `$cond`, `$trim`, `$map`, `$filter`, `$mergeObjects`** được dùng **bên trong** stage hợp lệ; chúng không trở thành stage mới.
4. Điều kiện chọn document phải nằm ở **filter**, không thêm `$match` vào update pipeline.
5. `$set` và `$unset` của pipeline là **aggregation stages**, khác với update operators cùng tên.
6. Khi dùng `$project` hoặc replacement stage, phải cẩn trọng với **mất field, _id bất biến và schema validation**.
7. `arrayFilters` không kết hợp với update pipeline; biến đổi mảng bằng biểu thức `$map`, `$filter` hoặc dùng cú pháp update truyền thống khi thích hợp.
8. Update trên **một document** có tính nguyên tử, còn `updateMany()` không mặc định là giao dịch nguyên tử trên nhiều document.
9. Dùng điều kiện filter, index và kiểm tra kết quả update để bảo đảm đúng phạm vi; thiết kế retry/idempotency cho các thao tác tăng hoặc trừ.

### Tài liệu MongoDB chính thức

- [Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/) — cú pháp, các stage được phép, `$literal` và ví dụ cập nhật.
- [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateone/) — filter, update pipeline, upsert, writeConcern và ngữ nghĩa của kết quả.
- [db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updatemany/) — cập nhật nhiều document và atomicity.
- [$set (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/set/) — thêm/ghi đè trường với expression.
- [$project (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/) — thay đổi cấu trúc trường của document.
- [$replaceWith (aggregation stage)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/replaceWith/) — thay đổi toàn bộ object gốc.
- [$map (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/) và [$filter (aggregation expression)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — tính toán các phần tử mảng.
- [MongoDB Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — tính nguyên tử của update và giao dịch nhiều document.
