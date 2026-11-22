# bulkWrite: kết hợp thêm, sửa, thay thế và xóa document

Trong một hệ thống thực tế, một tác vụ đồng bộ dữ liệu có thể cần **thêm** sản phẩm mới, **sửa** số lượng tồn kho, **thay thế** bản ghi đã chuẩn hóa, đồng thời **xóa** dữ liệu hết hiệu lực. Gửi từng lệnh `insertOne()`, `updateOne()`, `replaceOne()`, `deleteOne()` nối tiếp từ ứng dụng có thể phát sinh nhiều lượt trao đổi mạng và khó theo dõi kết quả. MongoDB cung cấp **`bulkWrite()`** để gom nhiều thao tác ghi vào một lời gọi cấp cao với lựa chọn về **thứ tự thực thi**, **xử lý lỗi** và **write concern**.

Bài học thuộc chương **Xóa và ghi theo lô** của module *Database Engine Document MongoDB*. Trọng tâm là **`db.collection.bulkWrite()`**, gồm sáu loại thao tác `insertOne`, `updateOne`, `updateMany`, `replaceOne`, `deleteOne` và `deleteMany`. Sau đó, bài phân biệt API này với `Mongo.bulkWrite()` đa collection xuất hiện từ MongoDB 8.0; hướng dẫn xử lý kết quả một phần, lỗi, retry, transaction, batching và rủi ro xóa nhầm dữ liệu.

Sau bài học, bạn có thể:

1. Dựng đúng **mảng write models** kết hợp insert, update, replace, delete.
2. Giải thích `ordered: true` và `ordered: false`, đặc biệt khi một thao tác thất bại.
3. Đọc các bộ đếm `insertedCount`, `matchedCount`, `modifiedCount`, `deletedCount`, `upsertedCount` và ID liên quan.
4. Biết vì sao **bulk write không mặc nhiên là một transaction**.
5. Dùng `upsert`, `arrayFilters`, `collation`, `hint` và điều kiện filter đúng ngữ cảnh.
6. Thiết kế retry/idempotency và xử lý các lỗi như duplicate key, validation failure hoặc write concern timeout.
7. Chọn kích thước batch hợp lý, tối ưu throughput mà không đánh đổi tính đúng đắn nghiệp vụ.

> **Phân biệt tên API theo phiên bản:** `db.collection.bulkWrite()` thao tác trên **một collection**. Từ **MongoDB 8.0**, server có thêm **`bulkWrite` database command** và `mongosh` có **`Mongo.bulkWrite()`** để ghi trên **nhiều collection/database** trong một lời gọi. Hai API **không dùng cùng một hình dạng operation object**. Phần lớn ví dụ bên dưới dành cho `db.collection.bulkWrite()` và có thể áp dụng ở MongoDB 7.0/8.0 và các phiên bản hỗ trợ tương ứng.

## 1. bulkWrite giải quyết bài toán gì?

Giả sử một đợt nhập dữ liệu cần:

~~~text
1. Insert sản phẩm mới P-400.
2. Cộng thêm tồn kho cho P-100.
3. Gắn cờ khuyến mãi cho sản phẩm phụ kiện.
4. Thay thế toàn bộ bản mô tả chuẩn hóa của P-300.
5. Xóa một bản ghi legacy theo ID.
6. Xóa những bản ghi inactive đã được chọn.
7. Nếu chưa có P-500 thì tạo bằng upsert.
~~~

Thay vì viết bảy lần gọi CRUD riêng:

~~~javascript
// Nhiều lệnh riêng (minh họa tư duy, không phải bulk):
products.insertOne(...)
products.updateOne(...)
products.updateMany(...)
products.replaceOne(...)
products.deleteOne(...)
products.deleteMany(...)
products.updateOne(..., { upsert: true })
~~~

Ta có thể mô tả chúng trong **một danh sách operation models**:

~~~javascript
const result = products.bulkWrite(
  [
    { insertOne: { document: /* ... */ } },
    { updateOne: { filter: /* ... */, update: /* ... */ } },
    { updateMany: { filter: /* ... */, update: /* ... */ } },
    { replaceOne: { filter: /* ... */, replacement: /* ... */ } },
    { deleteOne: { filter: /* ... */ } },
    { deleteMany: { filter: /* ... */ } }
  ],
  { ordered: true }
)
~~~

Lợi ích chính:

- **Giảm overhead phía client/network** so với tự phát nhiều lời gọi đơn lẻ không cần thiết.
- **Kết hợp nhiều loại write** trong cùng một collection và nhận kết quả tổng hợp.
- Điều khiển **dừng khi lỗi đầu tiên** hay **tiếp tục các thao tác độc lập**.
- Dễ tạo batch khi import, migration, đồng bộ cache/dữ liệu hoặc xử lý hàng loạt.

Giới hạn quan trọng:

- Một lời gọi `bulkWrite()` **không tạo atomicity cho cả danh sách**. Mỗi thao tác đơn document vẫn có atomicity riêng; `updateMany`/`deleteMany` có thể tác động nhiều document, không tự là transaction của toàn batch.
- `ordered: false` **không hứa giữ thứ tự** của các thao tác.
- Một số thao tác có thể thành công trước khi xuất hiện lỗi; ứng dụng phải đọc đúng kết quả.
- Batching vẫn chịu **giới hạn số thao tác/command, kích thước BSON, cache, tải ghi và write concern**.

## 2. Cú pháp tổng quát

Trong `mongosh`:

~~~javascript
db.collection.bulkWrite(
  [
    { insertOne: { document: { /* dữ liệu */ } } },
    { updateOne: {
        filter: { /* điều kiện */ },
        update: { $set: { /* fields */ } },
        upsert: false
    } },
    { updateMany: {
        filter: { /* điều kiện */ },
        update: { $inc: { /* fields */ } }
    } },
    { replaceOne: {
        filter: { /* điều kiện */ },
        replacement: { /* cả document thay thế */ },
        upsert: false
    } },
    { deleteOne: { filter: { /* điều kiện */ } } },
    { deleteMany: { filter: { /* điều kiện */ } } }
  ],
  {
    ordered: true,
    bypassDocumentValidation: false
  }
)
~~~

**Tham số thứ nhất** là array các operation objects. Mỗi object chứa **đúng một loại thao tác**. **Tham số thứ hai** là options chung của bulk, ví dụ `ordered`, `bypassDocumentValidation` và tùy API/phiên bản có `writeConcern` hoặc `let`.

Không viết:

~~~javascript
// Sai: nhầm API của helper đơn lẻ với hình dạng bulk operation.
db.products.bulkWrite([
  { insertOne: { _id: "P-1", name: "Book" } },
  { updateOne: { _id: "P-1", $set: { stock: 5 } } }
])
~~~

Thay vào đó, dùng các key `document`, `filter`, `update`, `replacement` đúng theo từng operation:

~~~javascript
db.products.bulkWrite([
  {
    insertOne: {
      document: { _id: "P-1", name: "Book", stock: 0 }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-1" },
      update: { $set: { stock: 5 } }
    }
  }
])
~~~

Ví dụ này **phụ thuộc thứ tự**, vì thao tác thứ hai muốn thấy document vừa được insert. Nếu mục đích đúng như vậy, hãy giữ `ordered: true`; **không** chuyển sang unordered chỉ để mong nhanh hơn.

## 3. Sáu thao tác trong collection bulkWrite

| Operation | Tác dụng | Field quan trọng | Số document có thể tác động |
|---|---|---|---|
| **`insertOne`** | Thêm một document. | `document` | Một document mới. |
| **`updateOne`** | Sửa một document khớp filter. | `filter`, `update`, tùy chọn `upsert` | Tối đa một document sửa/tạo. |
| **`updateMany`** | Sửa mọi document khớp filter. | `filter`, `update`, tùy chọn `upsert` | Có thể nhiều document. |
| **`replaceOne`** | Thay nội dung một document bằng replacement document. | `filter`, `replacement`, tùy chọn `upsert` | Tối đa một document sửa/tạo. |
| **`deleteOne`** | Xóa tối đa một document khớp filter. | `filter` | 0 hoặc 1 document. |
| **`deleteMany`** | Xóa mọi document khớp filter. | `filter` | Có thể nhiều document. |

### 3.1. `insertOne` — thêm một document

~~~javascript
{
  insertOne: {
    document: {
      _id: "P-400",
      sku: "NOTE-400",
      name: "Sổ kẻ dòng",
      category: "accessory",
      stock: 20,
      active: true
    }
  }
}
~~~

`document` chứa dữ liệu BSON cần insert. Nếu không cung cấp `_id`, client/driver hoặc server sẽ tạo ObjectId theo ngữ cảnh; ứng dụng cần ID ổn định cho retry/idempotency nên cân nhắc dùng **business key unique** và/hoặc ID xác định trước.

Nếu `_id` hoặc key trong **unique index** đã tồn tại, thao tác có thể báo **duplicate key**, không tự ghi đè document cũ. Muốn đồng bộ kiểu “có thì sửa, chưa có thì thêm”, cân nhắc **upsert** thay vì insert lặp vô điều kiện.

### 3.2. `updateOne` — sửa tối đa một document

~~~javascript
{
  updateOne: {
    filter: { _id: "P-100", active: true },
    update: {
      $inc: { stock: 5 },
      $set: { lastRestockedAt: ISODate("2026-11-14T00:00:00Z") }
    }
  }
}
~~~

MongoDB tìm document phù hợp `filter` và áp dụng `update`. Với `updateOne`, nếu nhiều document cùng khớp, chỉ một document được chọn; đừng dựa vào “document đầu tiên” nếu filter không xác định rõ business identity. Muốn sửa tất cả, phải dùng `updateMany` hoặc thiết kế thêm điều kiện.

`$inc` là phép tăng **nguyên tử trên một document**, giúp tránh lost update kiểu đọc stock về client rồi `$set` giá trị cũ. Nhưng nếu **toàn request được gửi lại** sau kết quả không rõ, `$inc` có thể tăng **hai lần** ở mức nghiệp vụ; cần phân biệt atomicity với idempotency.

### 3.3. `updateMany` — sửa mọi document khớp

~~~javascript
{
  updateMany: {
    filter: { category: "accessory", active: true },
    update: { $set: { promotionEligible: true } }
  }
}
~~~

`updateMany` áp dụng update cho tất cả document khớp **tại thời điểm được xử lý** theo ngữ nghĩa MongoDB, và mỗi document được sửa là nguyên tử. Toàn bộ những thay đổi **không phải một thao tác nguyên tử chung**. Nếu workload đồng thời thay `category`/`active`, số document thực sự bị sửa có thể thay đổi theo thời điểm.

Hãy kiểm tra filter bằng `find` và `countDocuments` trước các batch lớn. Một filter rỗng `{}` trong `updateMany` có thể cập nhật **cả collection** — có thể đúng nếu được thiết kế, nhưng rất nguy hiểm nếu vô ý.

### 3.4. `replaceOne` — thay toàn bộ document

~~~javascript
{
  replaceOne: {
    filter: { _id: "P-300" },
    replacement: {
      _id: "P-300",
      sku: "PEN-300",
      name: "Bút gel",
      category: "stationery",
      stock: 15,
      active: true,
      normalized: true
    }
  }
}
~~~

`replacement` phải là **document thay thế**, **không** phải biểu thức cập nhật chứa `$set`, `$inc`. Các field cũ **không có trong replacement sẽ biến mất** (ngoại trừ những quy tắc bảo toàn `_id`). Đây là khác biệt lớn nhất so với `updateOne` dùng update operators.

Document sau replace không được đổi giá trị `_id` sang một ID khác. Nếu muốn chỉ thay `name` hay `stock` mà giữ các field khác, dùng `updateOne` với `$set`; **không** dùng `replaceOne` bằng một object thiếu field.

### 3.5. `deleteOne` — xóa tối đa một document

~~~javascript
{
  deleteOne: {
    filter: { _id: "P-OLD1", legacy: true }
  }
}
~~~

Filter càng cụ thể càng dễ kiểm soát. Nếu `filter` khớp nhiều document, `deleteOne` chỉ xóa một document không được bạn xác định bằng thứ tự tùy ý. Để xóa đúng đối tượng, ưu tiên `_id` hoặc key duy nhất cùng các điều kiện bảo vệ.

### 3.6. `deleteMany` — xóa nhiều document

~~~javascript
{
  deleteMany: {
    filter: { active: false, archived: true }
  }
}
~~~

`deleteMany` có thể xóa **rất nhiều** document. Việc xóa nhiều document không được đảm bảo nguyên tử cho **toàn tập** nếu không dùng transaction. Không đặt `filter: {}` trừ khi mục đích được phê duyệt là xóa **toàn bộ collection**.

Nếu nghiệp vụ cần khôi phục, audit, thời gian giữ dữ liệu hoặc sự kiện đồng bộ, **soft delete** (ví dụ `$set: { deletedAt: ... }`) có thể phù hợp hơn hard delete. Đây là quyết định nghiệp vụ riêng, không phải tùy chọn của `deleteMany`.

## 4. Thực hành trọn vẹn: một bulk kết hợp sáu loại thao tác

### 4.1. Chuẩn bị dữ liệu thử nghiệm

Các lệnh bên dưới chỉ dành cho database `bulk_lab`. Chúng đặt lại các document demo có ID cố định; không chạy trên production. Để giữ kết quả minh họa có thể tái tạo, chỉ dùng collection lab riêng, chưa có dữ liệu ngoài danh sách mẫu.

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
const products = lab.products

// Chỉ chạy lần đầu trên collection thử nghiệm trống,
// hoặc dùng một collection lab riêng mới cho mỗi lần thực hành.
products.insertMany([
  {
    _id: "P-100", sku: "BOOK-100", name: "Sách A",
    category: "book", stock: 10, active: true
  },
  {
    _id: "P-200", sku: "PENCIL-200", name: "Bút chì",
    category: "accessory", stock: 5, active: true
  },
  {
    _id: "P-300", sku: "PEN-300", name: "Bút gel bản cũ",
    category: "stationery", stock: 12, active: true,
    legacyDescription: "Sẽ bị bỏ khi replace"
  },
  {
    _id: "P-OLD1", sku: "LEGACY-OLD1", name: "Sản phẩm cũ",
    category: "legacy", stock: 0, active: false, legacy: true
  },
  {
    _id: "P-DIS1", sku: "DISABLED-1", name: "Ngừng bán 1",
    category: "legacy", stock: 0, active: false, archived: true
  },
  {
    _id: "P-DIS2", sku: "DISABLED-2", name: "Ngừng bán 2",
    category: "legacy", stock: 0, active: false, archived: true
  }
])

products.find({}, { _id: 1, sku: 1, stock: 1, active: 1 })
  .sort({ _id: 1 })
~~~

**Nếu chạy lại bài sau khi đã insert**, `insertMany` với cùng `_id` sẽ gây duplicate key. Có thể tạo một database lab khác, hoặc chủ động reset **chỉ dữ liệu demo** sau khi chắc chắn bạn không chia sẻ collection với người khác. Không sử dụng `db.dropDatabase()` trên môi trường dùng chung chỉ để thử lệnh.

### 4.2. Thực hiện bulk có thứ tự

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
const products = lab.products

const operations = [
  // 0. Insert sản phẩm mới.
  {
    insertOne: {
      document: {
        _id: "P-400", sku: "NOTE-400", name: "Sổ kẻ dòng",
        category: "accessory", stock: 20, active: true
      }
    }
  },

  // 1. Update một sản phẩm bằng $inc và $set.
  {
    updateOne: {
      filter: { _id: "P-100", active: true },
      update: {
        $inc: { stock: 5 },
        $set: { lastRestockedAt: ISODate("2026-11-14T00:00:00Z") }
      }
    }
  },

  // 2. Update tất cả phụ kiện còn active.
  {
    updateMany: {
      filter: { category: "accessory", active: true },
      update: { $set: { promotionEligible: true } }
    }
  },

  // 3. Replace toàn bộ P-300 bằng document chuẩn hóa.
  {
    replaceOne: {
      filter: { _id: "P-300" },
      replacement: {
        _id: "P-300", sku: "PEN-300", name: "Bút gel",
        category: "stationery", stock: 15, active: true,
        normalized: true
      }
    }
  },

  // 4. Xóa chính xác một bản ghi legacy.
  {
    deleteOne: {
      filter: { _id: "P-OLD1", legacy: true }
    }
  },

  // 5. Xóa các bản ghi đã archived và inactive.
  {
    deleteMany: {
      filter: { active: false, archived: true }
    }
  },

  // 6. Upsert P-500 nếu chưa có.
  {
    updateOne: {
      filter: { _id: "P-500" },
      update: {
        $setOnInsert: {
          sku: "BAG-500", name: "Túi đựng tài liệu",
          category: "accessory", stock: 8, active: true
        }
      },
      upsert: true
    }
  }
]

const result = products.bulkWrite(operations, { ordered: true })
printjson(result)
~~~

Các operation được đặt trong một **mảng**; `ordered: true` là mặc định và bảo toàn sự phụ thuộc logic giữa thao tác 0 và 2. Vì thế `updateMany` ở vị trí 2 thấy được P-400 vừa insert ở vị trí 0, nếu bulk đến vị trí đó mà không gặp lỗi.

Nếu chạy đúng một lần trên dữ liệu chuẩn bị, kết quả kỳ vọng:

| Bộ đếm | Giá trị kỳ vọng | Lý do |
|---|---:|---|
| `insertedCount` | 1 | Insert P-400. |
| `matchedCount` | 4 | UpdateOne P-100 (1), UpdateMany P-200/P-400 (2), ReplaceOne P-300 (1). |
| `modifiedCount` | 4 | Bốn document khớp trên đều thay đổi giá trị. |
| `deletedCount` | 3 | DeleteOne P-OLD1 (1), DeleteMany P-DIS1/P-DIS2 (2). |
| `upsertedCount` | 1 | UpdateOne với upsert tạo P-500. |

Các giá trị này chỉ đúng với **collection lab ban đầu** và đúng thứ tự thao tác. Chạy lặp lại có thể gây duplicate key ở insert P-400, và không thể kỳ vọng các bộ đếm như lần đầu.

### 4.3. Xem trạng thái sau bulk

~~~javascript
products.find(
  {},
  {
    _id: 1, sku: 1, name: 1, stock: 1,
    promotionEligible: 1, archived: 1, normalized: 1
  }
).sort({ _id: 1 })
~~~

Dự kiến còn các document P-100, P-200, P-300, P-400, P-500. P-100 có `stock = 15`; P-200 và P-400 có `promotionEligible: true`; P-300 đã bỏ `legacyDescription` vì `replaceOne` thay toàn bộ document; P-OLD1, P-DIS1, P-DIS2 đã bị xóa; P-500 được tạo qua upsert.

**Bài học từ ví dụ:** Bulk có thể kết hợp nhiều kiểu ghi, nhưng điều đó không khiến số lượng thay đổi trở nên bất biến theo thời gian. Kết quả phụ thuộc dữ liệu đầu vào, thứ tự, filter và các ghi đồng thời từ client khác.

## 5. Ordered và unordered: cùng danh sách, hai ngữ nghĩa khác nhau

**`ordered`** quyết định MongoDB có phải thực hiện operation theo thứ tự trong danh sách và dừng khi gặp lỗi hay không.

| Tùy chọn | Cách thực thi | Khi có lỗi thao tác | Phù hợp khi |
|---|---|---|---|
| **`ordered: true`** (mặc định) | Thực thi theo thứ tự đã khai báo; mỗi bước đứng trước bước sau. | Dừng các operation kế tiếp sau lỗi write, trừ những trường hợp xử lý lỗi đặc thù như write concern. | Các operation **phụ thuộc lẫn nhau**, cần dễ suy luận thứ tự. |
| **`ordered: false`** | Server/driver có thể xử lý không theo thứ tự, có thể song song tùy điều kiện. | Tiếp tục thử những operation khác, những thao tác hợp lệ có thể thành công. | Các operation **độc lập**, cần throughput và chấp nhận kết quả một phần. |

Lưu ý:

- `ordered: true` **không** biến batch thành transaction; nó chỉ kiểm soát trình tự và cách dừng.
- `ordered: false` **không có cam kết** operation thứ 0 hoàn tất trước thứ 1, ngay cả khi chúng nằm trong một array được sắp xếp.
- Tối ưu thực thi có thể thay đổi theo deployment, sharding, batching và driver; unordered **có thể** nhanh hơn chứ không bảo đảm nhanh hơn trong mọi workload.
- Nếu nhiều operation cùng sửa một document, kết quả có thể phụ thuộc thứ tự. Nếu cần thứ tự xác định, đừng chọn unordered.

### 5.1. Thí nghiệm duplicate key với ordered

Thử trên collection mới, tách khỏi `products` để kết quả rõ ràng:

~~~javascript
const lab = db.getSiblingDB("bulk_lab")

lab.orderedDemo.insertOne({ _id: "A", value: 1 })

const orderedOps = [
  { insertOne: { document: { _id: "B", value: 2 } } },
  { insertOne: { document: { _id: "A", value: 999 } } }, // duplicate
  { insertOne: { document: { _id: "C", value: 3 } } }
]

try {
  lab.orderedDemo.bulkWrite(orderedOps, { ordered: true })
} catch (err) {
  print("Ordered bulk failed: " + err.message)
}

lab.orderedDemo.find().sort({ _id: 1 })
~~~

Kết quả kỳ vọng trên collection mới chứa sẵn duy nhất A:

~~~text
Operation 0: insert B -> thành công
Operation 1: insert A -> duplicate key
Operation 2: insert C -> KHÔNG được thực hiện

Document còn lại: A, B.
~~~

Tức là **B vẫn được insert** dù cả lời gọi bulk báo lỗi. Ordered **không rollback** những operation đã thực hiện trước lỗi.

### 5.2. Cùng dữ liệu nhưng unordered

~~~javascript
const lab = db.getSiblingDB("bulk_lab")

lab.unorderedDemo.insertOne({ _id: "A", value: 1 })

const unorderedOps = [
  { insertOne: { document: { _id: "B", value: 2 } } },
  { insertOne: { document: { _id: "A", value: 999 } } }, // duplicate
  { insertOne: { document: { _id: "C", value: 3 } } }
]

try {
  lab.unorderedDemo.bulkWrite(unorderedOps, { ordered: false })
} catch (err) {
  print("Unordered bulk reported one or more errors")
  print(err.message)
}

lab.unorderedDemo.find().sort({ _id: 1 })
~~~

Kết quả kỳ vọng trên collection demo mới:

~~~text
Insert A -> duplicate key, báo lỗi
Insert B -> có thể thành công
Insert C -> có thể thành công

Document còn lại: A, B, C.
~~~

**Không suy rằng B chắc chắn được insert trước C.** Khi viết test, chỉ khẳng định các operation độc lập hợp lệ đã được xử lý, không cố assert một thứ tự thời gian thực thi.

Nếu chạy ví dụ nhiều lần trên cùng collection, cả B và C đã tồn tại và sẽ báo duplicate key ở các lần kế tiếp; hãy đổi tên collection lab hoặc chuẩn bị lại dữ liệu theo mục tiêu thí nghiệm.

### 5.3. Vì sao unordered nguy hiểm khi operation phụ thuộc nhau?

Ví dụ:

~~~javascript
products.bulkWrite([
  {
    insertOne: {
      document: { _id: "P-X", stock: 0 }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-X" },
      update: { $inc: { stock: 5 } }
    }
  }
], { ordered: false })
~~~

Tưởng tượng update chạy trước insert: update có thể `matchedCount = 0`, rồi insert tạo stock 0. Kết quả nghiệp vụ mong muốn (stock 5) **không được đảm bảo**. Với dependency như vậy, dùng `ordered: true`, hoặc gộp thành **upsert** nếu nghiệp vụ phù hợp:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-X" },
      update: {
        $inc: { stock: 5 },
        $setOnInsert: { createdBy: "inventory-import" }
      },
      upsert: true
    }
  }
])
~~~

Ví dụ này có `$inc` nên **không idempotent nếu chính bulk được ứng dụng chủ động gửi lại** sau khi đã thành công. Để đảm bảo xử lý một sự kiện nhập kho đúng một lần, cần khóa định danh sự kiện/ledger hoặc một thiết kế chống xử lý lặp phù hợp.

## 6. Đọc kết quả trả về

Khi bulk được xác nhận thành công, `db.collection.bulkWrite()` trả một đối tượng chứa các bộ đếm và một số ánh xạ ID theo API hiện hành.

~~~javascript
const result = products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { checked: true } }
    }
  }
])

printjson(result)
~~~

Các field quan trọng:

| Field | Ý nghĩa |
|---|---|
| **`acknowledged`** | Có xác nhận ghi theo write concern hay không (khi API cung cấp). |
| **`insertedCount`** | Số thao tác `insertOne` thêm document thành công. |
| **`matchedCount`** | Tổng số document khớp filter của các thao tác update/replace. |
| **`modifiedCount`** | Số document thực sự được sửa; có thể nhỏ hơn `matchedCount` nếu giá trị không thay đổi. |
| **`deletedCount`** | Tổng document bị xóa bởi `deleteOne`/`deleteMany`. |
| **`upsertedCount`** | Số document được tạo bởi các operation `upsert: true`. |
| **`insertedIds`** | Ánh xạ chỉ số operation insert tới `_id` tương ứng khi API cung cấp. |
| **`upsertedIds`** | Ánh xạ chỉ số operation upsert tới `_id` được tạo khi API cung cấp. |

Ví dụ nếu `updateOne` match đúng document nhưng `$set: {checked:true}` trong khi giá trị đã là `true` thì thường:

~~~text
matchedCount: 1
modifiedCount: 0
~~~

Điều này **không phải lỗi**. Ngược lại, một `updateOne` có filter không khớp sẽ có `matchedCount = 0` và nếu không `upsert` thì không tạo document nào.

### 6.1. `matchedCount` khác `modifiedCount`

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { status: "ACTIVE" } }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { status: "ACTIVE" } }
    }
  }
])
~~~

Nếu ban đầu P-100 chưa có `status`, operation đầu tạo field và operation sau không thay đổi gì; tổng thường là `matchedCount = 2`, `modifiedCount = 1`. Vì có hai **operation** cùng match một document, bộ đếm là **tổng kết quả các operation**, không phải số lượng document ID duy nhất trong toàn batch.

### 6.2. ID upsert và chỉ số trong operations

Giả sử:

~~~javascript
const result = products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-600" },
      update: { $setOnInsert: { sku: "NEW-600" } },
      upsert: true
    }
  },
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { updated: true } }
    }
  }
])

printjson(result.upsertedIds)
~~~

Nếu P-600 chưa tồn tại, upsert sinh ra ID P-600; entry tương ứng thuộc **operation index 0**. **Không** nhầm `upsertedIds` với `insertedIds`: một upsert phát sinh từ `updateOne` hoặc `replaceOne` không phải operation `insertOne`.

Tùy ngôn ngữ driver, tên property và kiểu ánh xạ có thể khác. Trong Java Sync Driver, ví dụ, kết quả dùng `BulkWriteResult` và danh sách `BulkWriteUpsert`; phải đọc đúng tài liệu API.

### 6.3. Kết quả khi có lỗi không giống kết quả thành công

Nếu một operation thất bại, `bulkWrite()` có thể **throw exception** thay vì trả đối tượng result như bình thường. Trong `mongosh` thường là nhóm lỗi `BulkWriteError` / `MongoBulkWriteError` tùy phiên bản. Các thông tin hữu ích:

- **`writeErrors`**: các lỗi ở những operation cụ thể (ví dụ duplicate key, validation failure).
- **operation index**: vị trí trong danh sách operations (thường 0-based, cần đọc ngữ nghĩa theo driver).
- **`writeConcernErrors`**: lỗi đạt điều kiện xác nhận ghi (không đồng nghĩa chắc chắn chưa ghi).
- **partial result**: các số lượng đã thành công, nếu API cung cấp trong exception.

Không nên giả định mọi phiên bản driver đều trả cùng một object shape, hay mọi exception đều có đầy đủ `result.insertedIds`. Khi ghi báo cáo production, nên log **loại lỗi, code, index, batch ID** và bộ đếm có sẵn, nhưng tránh log toàn bộ dữ liệu khách hàng trong command.

### 6.4. Bảng xử lý lỗi theo loại

| Lỗi | Khả năng ảnh hưởng | Hướng xử lý |
|---|---|---|
| Duplicate key, thường `11000` | Một insert/upsert vi phạm unique key. | Kiểm tra ID/bất biến; có thể coi là “đã xử lý” nếu nghiệp vụ và dữ liệu thực tế xác nhận. |
| DocumentValidationFailure, thường `121` | Document không hợp validator. | Sửa dữ liệu/schema; không retry mù cùng payload. |
| Unauthorized | Account thiếu quyền cho operation/collection. | Sửa phân quyền, không tăng quyền tùy tiện. |
| Write concern timeout | Không đạt yêu cầu xác nhận trong thời gian đặt. | Kiểm tra kết quả thực tế/replica trước khi gửi lại các thao tác không idempotent. |
| Network timeout / primary stepdown | Không chắc client đã nhận kết quả đầy đủ. | Dùng retryable writes ở trường hợp hỗ trợ; reconcile theo ID/ledger. |
| Write conflict / transaction abort | Tranh chấp ghi theo engine/transaction. | Retry đúng cấp độ transaction hoặc operation theo lỗi/driver. |
| BSON document quá lớn | Một document không hợp giới hạn hệ thống. | Thay mô hình dữ liệu, không chỉ giảm kích thước batch. |
| Hint trỏ index không tồn tại | Operation không thực thi theo index được yêu cầu. | Kiểm tra index và rollout schema/index trước. |

## 7. Upsert: “nếu có thì sửa, nếu chưa có thì tạo”

`upsert: true` được hỗ trợ bởi `updateOne`, `updateMany` và `replaceOne`. Nếu **không có document nào khớp filter**, MongoDB có thể tạo document mới.

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-700" },
      update: {
        $set: { name: "Sản phẩm 700", active: true },
        $setOnInsert: {
          createdAt: ISODate("2026-11-14T00:00:00Z")
        }
      },
      upsert: true
    }
  }
])
~~~

Nếu P-700 chưa có, upsert chèn P-700 với field thích hợp. Nếu đã có, chỉ các update operators phù hợp được áp dụng; `$setOnInsert` **không ghi lại createdAt** cho document đã tồn tại.

### 7.1. `updateMany` với upsert không tạo “nhiều document mới”

Khi `updateMany` có `upsert: true` và không tìm thấy document nào, MongoDB **tạo một document mới**, không phải một document cho mỗi item tưởng tượng trong điều kiện tìm kiếm. Đừng dùng `updateMany + upsert` để biến một danh sách 100 sản phẩm thành 100 insert; hãy tạo 100 write models riêng, hoặc lựa chọn phương án insert phù hợp.

### 7.2. `replaceOne` với upsert

~~~javascript
products.bulkWrite([
  {
    replaceOne: {
      filter: { _id: "P-800" },
      replacement: {
        _id: "P-800",
        sku: "REPLACE-800",
        name: "Bản chuẩn hóa 800",
        stock: 4,
        active: true
      },
      upsert: true
    }
  }
])
~~~

Nếu P-800 chưa tồn tại, nó được tạo bằng replacement. Nếu đã tồn tại, document cũ bị **thay toàn bộ** (không đổi `_id`), những field không có trong replacement biến mất. Khác với `$setOnInsert`, replace upsert không tự phân biệt “giữ field hiện có” nếu application đã truyền một replacement không đầy đủ.

### 7.3. Chống race khi nhiều client cùng upsert

Nếu hai client cùng chạy upsert cho `sku = "BOOK-100"` mà collection không có unique index thích hợp, có thể xuất hiện **nhiều document trùng business key** tùy điều kiện cạnh tranh. Muốn bảo vệ tính duy nhất, tạo unique index theo quy tắc nghiệp vụ:

~~~javascript
// Chỉ chạy khi dữ liệu hiện có không trùng sku.
products.createIndex({ sku: 1 }, { unique: true })
~~~

Thêm unique index **không đảm bảo mọi upsert cạnh tranh luôn tự hợp nhất thành công**; một client có thể gặp duplicate key và cần xử lý theo logic đồng bộ. Filter nên chọn đúng identity, không dùng một điều kiện rộng có thể match nhiều document rồi sửa nhầm bản ghi.

### 7.4. Idempotency không đồng nghĩa với upsert

| Operation | Chạy lại sau thành công có thể gây thay đổi thêm? |
|---|---|
| `$set: { status: "ACTIVE" }` lên đúng ID | Thường **không** tạo trạng thái mới ngoài yêu cầu. |
| `$inc: { stock: 1 }` | **Có**, chạy lại tăng thêm lần nữa. |
| `insertOne` với cùng `_id` | Lần sau báo duplicate key; cần phân loại “đã xử lý” theo nghiệp vụ. |
| `replaceOne` với cùng replacement | Có thể cho cùng trạng thái cuối, nhưng vẫn cần xét concurrent update. |
| `deleteOne` theo `_id` | Chạy lại thường xóa 0 document; nếu data/model thay đổi thì vẫn phải đánh giá. |
| `deleteMany` theo điều kiện rộng | Chạy lại có thể xóa **những document mới** vừa trở nên khớp filter. |
| `upsert + $setOnInsert` | Có thể đạt trạng thái ổn định nếu filter là unique identity. |
| `upsert + $inc` | Có thể tạo một lần nhưng tiếp tục tăng mỗi lần replay. |

Để xử lý event có định danh duy nhất, có thể lưu `eventId` trong một **ledger** với unique index và cập nhật nghiệp vụ có transaction/điều kiện thích hợp. Không nên coi `ordered`, `upsert` hay `retryWrites=true` là một giải pháp chống xử lý lặp tổng quát.

## 8. Những tùy chọn nâng cao theo từng operation

Không phải mọi option đều áp dụng cho cả sáu kiểu operation. Hãy phân biệt **options chung** truyền vào `bulkWrite(operations, options)` với **tùy chọn của một operation cụ thể**.

| Option | Cấp khai báo | Vai trò |
|---|---|---|
| `ordered` | Toàn bulk | Giữ thứ tự và dừng khi lỗi, hoặc cho phép unordered. |
| `writeConcern` | Toàn bulk (với API hỗ trợ) | Mức xác nhận ghi của MongoDB. |
| `bypassDocumentValidation` | Toàn bulk (nếu API hỗ trợ) | Ngoại lệ schema validation với quyền phù hợp. |
| `upsert` | `updateOne`, `updateMany`, `replaceOne` | Nếu không khớp, tạo document mới. |
| `collation` | Theo operation thích hợp | Quy tắc so sánh chuỗi theo locale/case/diacritics. |
| `arrayFilters` | `updateOne`, `updateMany` | Chọn phần tử array được positional update sửa. |
| `hint` | Theo update/replace (và delete tùy API/phiên bản) | Yêu cầu một index cụ thể cho filter. |
| Aggregation pipeline trong `update` | Update operations | Tính toán trường bằng pipeline thay vì modifier document. |

Đừng đưa `ordered: false` vào bên trong `updateOne` như thể đó là option riêng của update. Ngược lại, `arrayFilters` gắn với **operation update cụ thể**, không nằm chung với `ordered` cho toàn batch.

### 8.1. `arrayFilters` để cập nhật phần tử trong mảng

Giả sử collection `orders` có dữ liệu:

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
lab.orders.insertOne({
  _id: "O-100",
  status: "PACKING",
  items: [
    { sku: "BK-01", qty: 2, packed: false },
    { sku: "PN-02", qty: 5, packed: false }
  ]
})
~~~

Một `bulkWrite` có thể vừa đánh dấu item BK-01 trong O-100, vừa cập nhật một order khác:

~~~javascript
lab.orders.bulkWrite([
  {
    updateOne: {
      filter: { _id: "O-100" },
      update: {
        $set: { "items.$[line].packed": true }
      },
      arrayFilters: [
        { "line.sku": "BK-01" }
      ]
    }
  },
  {
    updateOne: {
      filter: { _id: "O-100", status: "PACKING" },
      update: { $set: { lastPackedAt: new Date() } }
    }
  }
], { ordered: true })
~~~

`$[line]` chọn **những phần tử `items` có SKU BK-01** trong mỗi document được update chọn. `arrayFilters` là option gắn với `updateOne` thứ nhất; operation thứ hai không dùng nó.

Nếu các thao tác trên cần đảm bảo những điều kiện nghiệp vụ phức tạp **cùng thay đổi nguyên tử trong một order**, có thể gộp vào **một `updateOne`** để tận dụng atomicity một document thay vì phụ thuộc hai thao tác riêng trong bulk.

### 8.2. `collation` cho so sánh chuỗi

Giả sử cần cập nhật mọi product thuộc category có cùng cách viết hoa/thường:

~~~javascript
products.bulkWrite([
  {
    updateMany: {
      filter: { category: "ACCESSORY" },
      update: { $set: { season: "winter" } },
      collation: { locale: "en", strength: 2 }
    }
  }
])
~~~

Collation này cho phép so sánh phù hợp quy tắc locale với phân biệt chữ hoa/thường ở mức chọn, nhưng hành vi cụ thể phụ thuộc các tùy chọn strength, locale và dữ liệu. Một **index không có cùng collation** có thể không tối ưu cho truy vấn; cần thiết kế index phù hợp access pattern và so sánh bằng `explain()` khi cần.

### 8.3. `hint` để chọn index

~~~javascript
products.createIndex({ category: 1, active: 1 })

products.bulkWrite([
  {
    updateMany: {
      filter: { category: "accessory", active: true },
      update: { $set: { inspected: true } },
      hint: { category: 1, active: 1 }
    }
  }
])
~~~

`hint` yêu cầu planner dùng một index cụ thể. Nếu index không tồn tại hoặc không hợp lệ, operation có thể trả lỗi. Đừng thêm hint chỉ vì nghĩ “chỉ định index luôn nhanh”: query planner có thể chọn index tốt hơn khi tải và dữ liệu thay đổi. Khi rollout, tạo index trước rồi mới deploy code sử dụng hint.

### 8.4. Aggregation pipeline update trong bulk

`updateOne` và `updateMany` có thể nhận **array pipeline** trong `update` ở các phiên bản hỗ trợ:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: [
        {
          $set: {
            stockStatus: {
              $cond: [
                { $gt: ["$stock", 0] },
                "IN_STOCK",
                "OUT_OF_STOCK"
              ]
            }
          }
        }
      ]
    }
  }
])
~~~

Ở đây `update` là **mảng các pipeline stages**, không phải `{ $set: ... }` của update modifier. Các pipeline update hỗ trợ **tập stage giới hạn** cho update; không thể dùng mọi aggregation stage tùy ý. `$set` trong pipeline nhận **aggregation expressions**, cho phép tính từ giá trị hiện tại của document.

Nếu yêu cầu chỉ là `$inc` một trường, update operator thông thường đơn giản và rõ ý hơn. Chỉ dùng pipeline update khi cần các phép biến đổi dựa trên nhiều field hoặc thao tác tính toán phức tạp.

### 8.5. `bypassDocumentValidation` không phải cách sửa dữ liệu sai

Nếu collection có JSON Schema validator, bulk ghi document vi phạm có thể bị từ chối theo `validationAction`. Một số API hỗ trợ:

~~~javascript
products.bulkWrite(
  [
    {
      insertOne: {
        document: {
          _id: "P-IMPORT",
          name: "Dữ liệu nhập từ nguồn cũ"
        }
      }
    }
  ],
  {
    ordered: true,
    bypassDocumentValidation: true
  }
)
~~~

`bypassDocumentValidation` là ngoại lệ có kiểm soát, yêu cầu **privilege `bypassDocumentValidation`** cùng quyền ghi. Nó **không** bỏ qua unique index, authentication, giới hạn BSON hoặc các lỗi khác. Trong các phiên bản MongoDB mới có mức schema `constraint`, khả năng bypass còn bị hạn chế theo quy định của server. Nên import vào **staging** và sửa dữ liệu khi có thể, thay vì cấp bypass cho ứng dụng dài hạn.

## 9. Batch size, giới hạn và hiệu năng

### 9.1. Một lời gọi bulk không nhất thiết là một request vật lý

Theo MongoDB Manual, MongoDB giới hạn mỗi **write command batch** tối đa **`maxWriteBatchSize`** operation; giá trị phổ biến là **100.000**. Driver API cấp cao tự chia danh sách quá lớn thành các nhóm nhỏ phù hợp. Ngoài số lượng, command còn chịu giới hạn payload/BSON và kích thước document.

~~~text
Ứng dụng tạo operations[0..N-1]
               |
               v
    Collection bulkWrite API
               |
       driver chia thành batches
               |
     +---------+----------+
     |         |          |
     v         v          v
  Batch A   Batch B    Batch C
     |         |          |
     +---------+----------+
               |
          MongoDB Server
~~~

Đừng nhầm:

- **Giới hạn một document BSON:** thông thường **16 MiB**.
- **Giới hạn số write operations trong một server batch:** `maxWriteBatchSize`, thường **100.000**.
- **Giới hạn kích thước command/message:** là ràng buộc khác, có thể khiến driver phải chia batch trước khi đạt 100.000.
- **Giới hạn bộ nhớ và tải ứng dụng:** một array vài trăm nghìn operation có thể tiêu tốn RAM lớn trước khi gửi.

Nếu trực tiếp dùng `db.runCommand()` và gửi một write command vượt giới hạn, server có thể báo lỗi thay vì tự chia. Phần chia batch là lợi ích của **high-level driver/shell API**, không phải bảo đảm với mọi raw command tự xây.

### 9.2. Kiểm tra `maxWriteBatchSize` từ server

~~~javascript
const hello = db.adminCommand({ hello: 1 })
printjson({
  maxWriteBatchSize: hello.maxWriteBatchSize,
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes
})
~~~

Không nên cố lập một batch bằng đúng giới hạn kỹ thuật. MongoDB có thể chia các operation theo loại command, kích thước và giới hạn nội bộ; cách nhóm là chi tiết triển khai có thể thay đổi theo driver/version.

### 9.3. Chọn kích thước batch ứng dụng

Ví dụ chia một danh sách thay đổi thành các nhóm **1.000 operations** là điểm bắt đầu để đánh giá, **không phải mức tối ưu chung**:

~~~javascript
const batchSize = 1000
const allOps = [] // Do pipeline ứng dụng tạo ra, minh họa.

for (let start = 0; start < allOps.length; start += batchSize) {
  const batch = allOps.slice(start, start + batchSize)
  const result = products.bulkWrite(batch, { ordered: false })
  print("Batch " + start + " done: " + result.insertedCount)
}
~~~

Ví dụ loop này **chưa xử lý lỗi**; chỉ minh họa cách chia, không được sao chép nguyên xi cho migration quan trọng. Trong production, mỗi batch cần **batch ID**, kết quả/exception, checkpoint và retry/reconcile idempotent.

Đo đạc trên workload thực để quyết định 100, 500, 1.000, 5.000 hay kích thước khác. Batch lớn có thể giảm overhead request, nhưng cũng tăng:

- bộ nhớ tại client và công việc server mỗi đợt;
- thời gian chờ một lời gọi;
- quy mô kết quả một phần cần khôi phục khi lỗi;
- áp lực replication/journal/cache và write conflicts nếu nhiều client cùng ghi.

Batch nhỏ hơn giúp theo dõi và retry theo đơn vị nhỏ nhưng có thể tăng network round trips. Cân bằng theo **throughput, p95 latency, số lỗi, memory và replication lag**, không chỉ nhìn tốc độ insert.

### 9.4. Ordered/unordered trên sharded cluster

Trên collection sharded, các operation có thể được phân phối đến những shard khác nhau. `ordered: true` yêu cầu giữ thứ tự, nên thao tác sau có thể phải chờ thao tác trước; unordered có cơ hội tối ưu và song song hơn nếu các operation độc lập.

Hãy chú ý **shard key**, mức độ targeted query, index filter và document hotspot. Một bulk gồm hàng nghìn update vào **cùng một `_id`** không tự trở nên song song hiệu quả chỉ vì `ordered: false`. Mục tiêu là phân phối tải ghi hợp lý, không tạo tranh chấp ở storage engine.

### 9.5. Index và chi phí ghi theo lô

Mỗi insert/update/delete có thể phải thay đổi nhiều index. Những index không cần thiết tăng chi phí ghi, nhưng xóa index tùy tiện sẽ làm truy vấn đọc chậm. Với cập nhật/xóa nhiều document:

~~~javascript
products.find(
  { category: "accessory", active: true },
  { _id: 1, sku: 1 }
).limit(20)

products.countDocuments({
  category: "accessory",
  active: true
})
~~~

Hãy kiểm tra **số lượng dự kiến** trước khi chạy operation rộng. Với query chậm, dùng `explain()` trên thao tác đọc tương đương hoặc công cụ profiler/slow log đúng môi trường để hiểu mức quét. **Không** coi bulk là giải pháp cho một filter thiếu index phải duyệt hàng triệu document.

### 9.6. Không giả định lỗi trả đủ thông điệp chi tiết

Với bulk rất lớn, lượng `writeErrors` có thể nhiều. MongoDB có giới hạn và có thể **truncate** phần văn bản của một số lỗi khi kích thước báo lỗi quá lớn. Vì thế, ngoài exception message, ứng dụng nên biết **operation index, batch ID và input ID** để xác định dữ liệu cần xử lý, không phụ thuộc duy nhất vào chuỗi lỗi từ server.

## 10. Retryable writes, lỗi mạng và idempotency

Retry là một trong những phần dễ gây sai lệch dữ liệu nhất khi dùng `bulkWrite()`. Có **ba lớp retry khác nhau**:

1. **Retry nội bộ ở storage engine:** MongoDB xử lý một số write conflicts khi thực thi thao tác, client có thể không thấy từng lần thử.
2. **Retryable writes của driver/server:** tài liệu MongoDB quy định một tập operation có thể được retry khi lỗi mạng hoặc failover theo điều kiện hỗ trợ.
3. **Retry ứng dụng:** job/scheduler/client chủ động gửi lại cả request hoặc cả batch sau khi thấy lỗi hoặc timeout.

Ba cơ chế này **không đồng nghĩa**; không được giả định “MongoDB đã có retryable writes thì batch bất kỳ đều an toàn để gửi lại từ đầu”.

### 10.1. Những bulk operations nào có thể retry tự động?

Theo tài liệu **Retryable Writes**, một `db.collection.bulkWrite()` chỉ gồm các **single-document write operations** sau mới thuộc nhóm **retryable** khi deployment/driver/write concern đáp ứng điều kiện:

- `insertOne`;
- `updateOne`;
- `replaceOne`;
- `deleteOne`.

Nếu trong batch có thao tác **multi-document** như `updateMany` hoặc `deleteMany`, lệnh gửi xuống server chứa chúng **không được bảo đảm retryable theo cơ chế retryable writes**. Driver có thể chia danh sách thành các write commands nội bộ, và tính retryable được đánh giá theo command thực tế sau khi phân nhóm. Không nên tự suy rằng một bulk hỗn hợp **chắc chắn** được retry toàn phần.

Các điều kiện cơ bản còn gồm:

- **Replica set hoặc sharded cluster** hỗ trợ session/retryable writes; **standalone** không hỗ trợ cơ chế này theo cùng cách.
- **Acknowledged write concern**; `w: 0` không hỗ trợ retryable writes.
- Driver/server version hỗ trợ; ứng dụng cấu hình `retryWrites` đúng.
- **Write bên trong transaction không được retry riêng lẻ** bằng cơ chế retryable writes; chỉ commit/abort có quy tắc retry riêng.

`retryWrites=true` không là bảo đảm **exactly-once business processing** cho toàn bộ nghiệp vụ, nhất là khi có side effects ngoài MongoDB hoặc request được gửi lại từ tầng khác.

### 10.2. Timeout không cho biết chắc ghi có xảy ra hay chưa

Giả sử ứng dụng gọi:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $inc: { stock: 5 } }
    }
  }
])
~~~

Server có thể đã tăng stock, nhưng **mất kết nối trước khi phản hồi tới client**. Nếu client tùy tiện gửi lại `$inc:5`, stock có thể tăng hai lần. Với những đường retry được MongoDB driver hỗ trợ, server/driver có cơ chế nhận diện lần thử lại theo session/statement. Nhưng **retry thủ công một request mới** sau khi ứng dụng mất dấu trạng thái không mặc nhiên được xem là retry cùng statement.

### 10.3. Thiết kế idempotent bằng trạng thái đích

Nếu nguồn đồng bộ đã có số tồn kho **chính xác tại mốc T** và mỗi sản phẩm có version tăng dần, một chiến lược có thể dùng **conditional update**:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: {
        _id: "P-100",
        inventoryVersion: { $lt: 42 }
      },
      update: {
        $set: {
          stock: 125,
          inventoryVersion: 42
        }
      }
    }
  }
])
~~~

Điều kiện có tác dụng khi document đã tồn tại và `inventoryVersion` là số có thứ tự hợp lệ: nếu job gửi lại version 42, document đang version 42 sẽ không khớp nữa. Tuy nhiên ví dụ **không tự xử lý document thiếu `inventoryVersion`**; schema và điều kiện cần được xây dựng cho cả dữ liệu legacy nếu có. Nếu có thể nhiều producers cập nhật inventory, phải xác định nguồn version chuẩn và bảo đảm chúng không tạo version xung đột.

Một mẫu khác là **sự kiện có ID duy nhất**:

~~~javascript
// Chỉ minh họa khóa dedupe, chưa đủ cho một nghiệp vụ nhiều document.
db.getSiblingDB("bulk_lab").processedEvents.createIndex(
  { eventId: 1 },
  { unique: true }
)
~~~

Ghi `eventId` duy nhất giúp phát hiện xử lý trùng. Nhưng nếu cần đồng thời tạo event ledger và cập nhật stock ở **hai document**, phải thiết kế transaction hoặc workflow bù trừ có tính nhất quán; chỉ tạo unique index ở ledger chưa tự khiến hai thay đổi nguyên tử cùng nhau.

### 10.4. Khôi phục sau bulk thất bại

Với workload quan trọng, một runbook có thể gồm:

~~~text
Input batch B-123 được lưu có ID cho từng operation
               |
        Gọi collection.bulkWrite
               |
        +------+------+
        |             |
       OK          Error / Timeout
        |             |
  Ghi checkpoint    Lấy error codes, indexes,
                    partial counts nếu có
                      |
               Đối soát trạng thái DB bằng
               business key / event ID
                      |
             Chỉ retry các thao tác còn thiếu
             hoặc đã thiết kế idempotent
~~~

Không dựa vào thông tin “đã xử lý tới operation index 150” khi dùng unordered như thể các index nhỏ hơn 150 đều thành công. Với unordered, kết quả có thể không liên tục; cần mapping từ **operation index → business identity** và biết cách kiểm tra trạng thái hiện tại.

## 11. Transaction và bulkWrite: khi nào cần commit hoặc abort toàn nhóm?

**`bulkWrite()` mặc định không phải transaction**. Ví dụ xóa 10 tài liệu và chèn 3 tài liệu trong cùng bulk có thể tạo **trạng thái trung gian** thấy được bởi client khác khi các thao tác chạy. Ordered không ngăn điều đó.

### 11.1. Khi bulk không cần transaction

Bulk không cần atomicity toàn nhóm khi:

- Mỗi thao tác độc lập, ví dụ cập nhật metadata của 500 sản phẩm khác nhau.
- Có thể chấp nhận kết quả một phần và xử lý lỗi bằng retry/reconciliation.
- Có thể chạy nhiều batch và có checkpoint.
- Trạng thái trung gian không phá vỡ bất biến nghiệp vụ quan trọng.

Đó là các tình huống tốt để dùng unordered nếu các thao tác thật sự độc lập.

### 11.2. Khi cần transaction nhiều document

Giả sử phải:

1. Trừ 10 đơn vị inventory document P-100.
2. Tạo một reservation document R-100.
3. Cập nhật order O-100 thành RESERVED.

Nếu **cả ba cùng commit hoặc cùng abort** là bất biến cần thiết, một `bulkWrite()` collection-scoped không giải quyết vì còn liên quan **nhiều collection**. Dùng transaction trong môi trường hỗ trợ, hoặc cân nhắc mô hình nghiệp vụ khác.

Ví dụ đơn giản trên **một collection** để thấy bulk có thể chạy trong transaction qua session:

~~~javascript
// Chạy trên replica set/sharded deployment hỗ trợ transactions.
// Demo dùng database riêng. Bỏ qua code retry transaction production.
const session = db.getMongo().startSession()
const coll = session.getDatabase("bulk_lab").transactionDemo

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  coll.bulkWrite([
    {
      insertOne: {
        document: { _id: "TX-A", value: 1 }
      }
    },
    {
      updateOne: {
        filter: { _id: "TX-A" },
        update: { $inc: { value: 1 } }
      }
    }
  ], { ordered: true })

  session.commitTransaction()
  print("Transaction committed")
} catch (error) {
  try { session.abortTransaction() } catch (_) {}
  print("Transaction did not complete normally: " + error.message)
} finally {
  session.endSession()
}
~~~

Đây là **ví dụ cấu trúc session/transaction**, không phải công thức xử lý retry đầy đủ. Không đặt `writeConcern` ở tùy chọn **từng bulk bên trong transaction**; write concern cần được xác định ở **transaction/commit** theo tài liệu. Trên standalone hoặc deployment không hỗ trợ transaction, ví dụ sẽ không chạy.

### 11.3. Lỗi trong transaction khác ngoài transaction

Ngoài transaction:

- **Ordered** dừng sau một write error; các operation trước đó vẫn có thể commit.
- **Unordered** tiếp tục thử những operation còn lại, kể cả khi một số operation bị lỗi.

Trong multi-document transaction, một lỗi ghi có thể dẫn tới **abort transaction**; không xem unordered như một cách “bỏ qua lỗi rồi vẫn commit các operation hợp lệ”. Driver và version có quy tắc riêng khi exception xảy ra trong transaction; cần xử lý theo transaction API.

### 11.4. Retry transaction

MongoDB phân biệt:

| Tín hiệu | Cách nghĩ đúng |
|---|---|
| `TransientTransactionError` | Một transaction đã thất bại tạm thời, có thể cần chạy lại **toàn transaction**. |
| `UnknownTransactionCommitResult` | Không chắc commit thành công hay chưa; cần **retry commit** theo API driver, không tự động replay nghiệp vụ. |
| `DuplicateKey` hoặc validation error | Dữ liệu/ràng buộc không hợp lệ; không retry mù. |
| Transaction quá lớn hoặc quá lâu | Giảm phạm vi/thời gian transaction; retry y nguyên thường không giúp. |

Các driver có **convenient transaction API** có thể tự retry theo một số nhãn lỗi. Nhưng nếu callback có thể chạy lại, đừng gửi email, gọi gateway thanh toán hay phát message bên ngoài một cách không có idempotency trong callback đó.

### 11.5. Bulk quá lớn không nên ép vào một transaction khổng lồ

Một transaction phải duy trì snapshot/lock/tài nguyên và có giới hạn thời gian; tập update khổng lồ có thể tốn cache và tăng conflict. Với migration có thể checkpoint và khôi phục theo lô, **nhiều bulk nhỏ, idempotent** thường phù hợp hơn một transaction khổng lồ nhằm “bảo đảm tất cả cùng thành công”.

Khi thực sự có bất biến nhiều document, chỉ đưa **những document thiết yếu** vào transaction. Tổ chức batch theo transaction boundary của nghiệp vụ, không theo số lượng operations tùy ý.

## 12. MongoDB 8.0+: phân biệt `Mongo.bulkWrite()` nhiều namespace

MongoDB **8.0** bổ sung `bulkWrite` database command và `Mongo.bulkWrite()` trong `mongosh`, cho phép một lời gọi ghi lên **nhiều collection, thậm chí nhiều database**.

### 12.1. So sánh trực tiếp

| Khía cạnh | `db.collection.bulkWrite()` | `Mongo.bulkWrite()` |
|---|---|---|
| Phạm vi | **Một collection**. | **Nhiều namespace** dạng `database.collection`. |
| Phiên bản | Có từ các dòng MongoDB trước 8.0. | Yêu cầu **MongoDB 8.0+**. |
| Hình dạng operation | `{ insertOne: { document: ... } }`. | `{ namespace: "...", name: "insertOne", document: ... }`. |
| Các loại thao tác | InsertOne, UpdateOne, UpdateMany, ReplaceOne, DeleteOne, DeleteMany. | Cũng hỗ trợ các loại thao tác tương ứng, qua field `name`. |
| Options/kết quả | API collection, result như `insertedIds`/`upsertedIds`. | API connection, có `verboseResults` và các map kết quả tùy option. |
| Transaction | Có thể dùng với session/transaction khi deployment hỗ trợ. | Trong transaction dùng `Session.bulkWrite()` theo tài liệu. |

Đừng nhầm `db.collection.bulkWrite()` với database command raw `bulkWrite` của MongoDB 8.0. Command raw có cấu trúc `ops` và `nsInfo`, khác cả hai helper `mongosh`.

### 12.2. Ví dụ nhiều collection

~~~javascript
// Chỉ chạy MongoDB Server 8.0+.
const mongo = db.getMongo()

const result = mongo.bulkWrite([
  {
    namespace: "bulk_lab.products",
    name: "insertOne",
    document: {
      _id: "P-MULTI-1",
      name: "Sản phẩm bổ sung",
      stock: 2
    }
  },
  {
    namespace: "bulk_lab.auditEvents",
    name: "insertOne",
    document: {
      _id: "E-MULTI-1",
      type: "IMPORT",
      productId: "P-MULTI-1",
      at: new Date()
    }
  },
  {
    namespace: "bulk_lab.products",
    name: "updateOne",
    filter: { _id: "P-MULTI-1" },
    update: { $set: { active: true } }
  }
], {
  ordered: true,
  verboseResults: true
})

printjson(result)
~~~

Thao tác trên ghi vào **products** và **auditEvents**. Nhưng điều quan trọng vẫn đúng: **một lời gọi `Mongo.bulkWrite()` không tự có atomicity nhiều collection**. Nếu insert product thành công nhưng insert audit event thất bại, ordered chỉ dừng phần còn lại; muốn đảm bảo cả hai cùng commit, cần **transaction** hoặc mô hình ghi sự kiện phù hợp.

API `Mongo.bulkWrite()` trả các bộ đếm tổng hợp, và khi `verboseResults: true` có thể trả map kết quả theo operation. **Không** áp đặt shape của `db.collection.bulkWrite()` lên nó; ví dụ `upsertedIds`/`insertedIds` của API collection khác với các kết quả verbose của API mới. Xem tài liệu đúng server/mongosh version.

### 12.3. `Session.bulkWrite()` khi cần transaction đa namespace

Trong `mongosh`, tài liệu MongoDB 8.0+ hướng dẫn dùng **`Session.bulkWrite()`** để gắn multi-namespace bulk với session/transaction. Khi dùng trong transaction, cần:

- Deployment hỗ trợ multi-document transactions.
- Start/commit/abort thông qua session.
- Retry transaction theo nhãn lỗi và driver/shell API, không tự replay commit chưa rõ.
- Chỉ đưa các operation thuộc cùng đơn vị nghiệp vụ vào transaction.

Không lấy mảng operations của `Mongo.bulkWrite()` rồi gọi thẳng `db.collection.bulkWrite()`: hai API đòi các object khác nhau. Đây là một lỗi khi copy mẫu từ tài liệu MongoDB 8.0 sang ứng dụng dùng API collection cũ.

## 13. Sử dụng collection bulkWrite với MongoDB Java Sync Driver

Trong Java, MongoDB Sync Driver cung cấp **`MongoCollection.bulkWrite()`** nhận **`List<WriteModel<TDocument>>`** và `BulkWriteOptions`. Đây là API collection-scoped tương ứng với `db.collection.bulkWrite()` của `mongosh`.

### 13.1. Mapping từ mongosh sang Java

| Mongosh operation | Java driver model |
|---|---|
| `{insertOne:{document: ...}}` | `new InsertOneModel<>(document)` |
| `{updateOne:{filter,update}}` | `new UpdateOneModel<>(filter, update)` |
| `{updateMany:{filter,update}}` | `new UpdateManyModel<>(filter, update)` |
| `{replaceOne:{filter,replacement}}` | `new ReplaceOneModel<>(filter, replacement)` |
| `{deleteOne:{filter}}` | `new DeleteOneModel<>(filter)` |
| `{deleteMany:{filter}}` | `new DeleteManyModel<>(filter)` |
| `{ordered:false}` | `new BulkWriteOptions().ordered(false)` |
| `{upsert:true}` của update | `new UpdateOptions().upsert(true)` |

### 13.2. Ví dụ Java: trộn đủ sáu loại write

Giả sử biến `database` là `com.mongodb.client.MongoDatabase` đã kết nối tới database thử nghiệm:

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;
import com.mongodb.bulk.BulkWriteResult;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.DeleteManyModel;
import com.mongodb.client.model.DeleteOneModel;
import com.mongodb.client.model.InsertOneModel;
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.UpdateManyModel;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.Arrays;
import java.util.Date;
import java.util.List;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;
import static com.mongodb.client.model.Updates.setOnInsert;

// database: MongoDatabase trỏ tới "bulk_lab".
MongoCollection<Document> products = database.getCollection("products");

List<WriteModel<Document>> operations = Arrays.asList(
    new InsertOneModel<>(
        new Document("_id", "P-J400")
            .append("sku", "NOTE-J400")
            .append("name", "Sổ Java")
            .append("category", "accessory")
            .append("stock", 20)
            .append("active", true)
    ),

    new UpdateOneModel<>(
        eq("_id", "P-100"),
        combine(
            inc("stock", 5),
            set("lastRestockedAt", new Date())
        )
    ),

    new UpdateManyModel<>(
        and(
            eq("category", "accessory"),
            eq("active", true)
        ),
        set("promotionEligible", true)
    ),

    new ReplaceOneModel<>(
        eq("_id", "P-300"),
        new Document("_id", "P-300")
            .append("sku", "PEN-300")
            .append("name", "Bút gel chuẩn hóa")
            .append("stock", 15)
            .append("active", true)
    ),

    new DeleteOneModel<>(
        and(
            eq("_id", "P-OLD1"),
            eq("legacy", true)
        )
    ),

    new DeleteManyModel<>(
        and(
            eq("active", false),
            eq("archived", true)
        )
    ),

    new UpdateOneModel<>(
        eq("_id", "P-J500"),
        combine(
            setOnInsert("sku", "BAG-J500"),
            setOnInsert("name", "Túi Java"),
            setOnInsert("stock", 8),
            setOnInsert("active", true)
        ),
        new UpdateOptions().upsert(true)
    )
);

BulkWriteOptions options = new BulkWriteOptions().ordered(true);

try {
    BulkWriteResult result = products.bulkWrite(operations, options);

    System.out.println("inserted=" + result.getInsertedCount());
    System.out.println("matched=" + result.getMatchedCount());
    System.out.println("modified=" + result.getModifiedCount());
    System.out.println("deleted=" + result.getDeletedCount());
    System.out.println("upserts=" + result.getUpserts().size());
} catch (MongoBulkWriteException ex) {
    for (BulkWriteError error : ex.getWriteErrors()) {
        System.err.println(
            "operation index=" + error.getIndex()
            + ", code=" + error.getCode()
        );
    }
    // Kiểm tra kết quả thành công một phần qua ex.getWriteResult()
    // khi driver cung cấp, và kiểm tra writeConcernError riêng.
    // Không retry mù cả list chứa $inc hoặc deleteMany.
    throw ex;
}
~~~

Đây là **ví dụ minh họa API**, không phải một job production hoàn chỉnh: biến `database` cần được khởi tạo từ `MongoClient`, cần vòng đời connection rõ ràng và cần xác định chính sách xử lý partial failure. Không chạy lặp trên cùng collection demo vì `insertOne` P-J400 sẽ gặp duplicate key ở lần sau.

### 13.3. Lưu ý khi dùng POJO thay cho Document

Nếu collection là `MongoCollection<Product>` với POJO codec, các models là `WriteModel<Product>`, còn filters/updates vẫn được serialize theo mapping của driver. Khi có class inheritance, annotation, field alias hay `_id` mapping, phải kiểm tra cách BSON codec sinh document thực tế. Không tự thay `replaceOne` bằng một POJO thiếu field rồi mong database giữ nguyên các field cũ.

### 13.4. Đọc lỗi trong Java Driver

Với `MongoBulkWriteException`, cần phân loại:

- **`getWriteErrors()`**: danh sách lỗi từng operation; `getIndex()` có thể giúp map về phần tử input.
- **`getWriteConcernError()`**: lỗi xác nhận ghi, nếu có.
- **`getWriteResult()`**: kết quả từ các operation thành công, theo hợp đồng API.

Thông tin cụ thể phụ thuộc driver version. Để xử lý robust, lưu **batchId + operationId + business key** trước khi gọi bulk; exception chỉ là một phần bằng chứng. Không log nguyên document chứa dữ liệu cá nhân chỉ để debug duplicate key.

### 13.5. Bulk API theo Spring Data MongoDB

Trong Spring Data, `MongoTemplate.bulkOps(...)` cung cấp một builder API khác với `MongoCollection.bulkWrite()`. Cần chú ý:

- Kiểu operation và các tùy chọn có thể khác Java Sync Driver trực tiếp.
- `BulkMode.ORDERED` và `BulkMode.UNORDERED` diễn đạt tương tự ý định về thứ tự, nhưng phải kiểm tra phiên bản framework.
- Cơ chế entity lifecycle callbacks/auditing/versioning có những hạn chế riêng với bulk operations theo tài liệu Spring Data.
- Nếu cần optimistic locking với `@Version`, đừng mặc định bulk operation trực tiếp áp dụng tất cả lifecycle/concurrency checks của `save()`.

Khi không chắc một abstraction làm gì, xem **BSON command được gửi** và tài liệu phiên bản dependency thực tế. Không dùng snippet MongoDB shell rồi tự giả định tương đương 100% với API của framework.

## 14. Quy trình chạy một bulk thay đổi dữ liệu an toàn

Một bulk job đáng tin cậy cần được thiết kế như một **quy trình thay đổi dữ liệu có khả năng khôi phục**, không chỉ là một for-loop gom nhiều write models.

### 14.1. Bước 1 — Xác định input và identity

Với mỗi operation, lưu:

~~~text
batchId: import-2026-11-14-001
operationIndex: 17
operationId: inventory-event-987
type: updateOne
targetBusinessKey: P-100
expectedVersion: 42
desiredEffect: set stock = 125
~~~

**Operation index** giúp đối chiếu exception; **operationId/business key** cho phép đối soát thực tế sau lỗi hoặc replay. Nếu dữ liệu gốc đến từ Kafka, queue hoặc file ETL, nên dùng ID ổn định từ nguồn và checkpoint rõ ràng.

### 14.2. Bước 2 — Xác minh phạm vi update/delete

Trước `updateMany`/`deleteMany`, truy vấn đếm và lấy mẫu:

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
const filter = {
  active: false,
  archived: true
}

print("Expected candidates=" + lab.products.countDocuments(filter))
printjson(
  lab.products.find(filter, { _id: 1, sku: 1, active: 1 })
    .limit(20)
    .toArray()
)
~~~

Đếm trước và số xóa thật có thể **khác** nếu có ghi đồng thời giữa hai thời điểm. Bước preflight không tạo một lock giữ nguyên tập kết quả; nếu cần xóa đúng snapshot đã được phê duyệt, cân nhắc lưu **danh sách ID cụ thể**, áp dụng điều kiện version/updatedAt hoặc transaction phù hợp.

### 14.3. Bước 3 — Dùng filter có điều kiện bảo vệ

Thay vì:

~~~javascript
{
  deleteMany: {
    filter: { active: false }
  }
}
~~~

có thể sử dụng nhiều điều kiện hơn:

~~~javascript
{
  deleteMany: {
    filter: {
      active: false,
      archived: true,
      archivedAt: { $lt: ISODate("2025-01-01T00:00:00Z") },
      legalHold: { $ne: true }
    }
  }
}
~~~

Nhưng filter dài **chỉ thực sự an toàn nếu phản ánh đúng policy**. Ví dụ `legalHold: {$ne:true}` bao gồm field `legalHold` bị thiếu; nếu quy định yêu cầu field phải xác nhận rõ `false`, hãy dùng `legalHold: false` cùng schema phù hợp. Không coi mọi điều kiện `$ne` là từ chối tuyệt đối các bản ghi thiếu field.

### 14.4. Bước 4 — Chọn ordered hay unordered có chủ đích

~~~text
Các operations có dependency?
    |
    +-- Có --> ordered: true
    |           hoặc gộp thành một atomic update/transaction
    |
    +-- Không --> cân nhắc ordered: false để tăng throughput
                  nhưng bắt buộc xử lý kết quả một phần
~~~

**Dependency** có thể là dữ liệu (sửa document vừa insert), thứ tự trạng thái (PENDING → PAID → SHIPPED), hoặc điều kiện nghiệp vụ. Nếu cần sự kiện theo thứ tự nhưng bulk unordered, kết quả có thể sai dù tất cả operation riêng lẻ thành công.

### 14.5. Bước 5 — Thiết kế chunking và checkpoint

Với hàng trăm nghìn operations, chia thành các lô vừa phải:

~~~javascript
function runBatches(collection, batches) {
  for (const batch of batches) {
    // batch phải có ID, operations và log/checkpoint bên ngoài.
    try {
      const result = collection.bulkWrite(
        batch.operations,
        { ordered: false }
      )
      printjson({
        batchId: batch.id,
        inserted: result.insertedCount,
        matched: result.matchedCount,
        deleted: result.deletedCount
      })
      // Production: lưu checkpoint sau khi xác minh kết quả.
    } catch (err) {
      print("Batch failed: " + batch.id)
      print(err.message)
      // Production: đối soát từng operation; không tự đánh dấu hoàn tất.
      throw err
    }
  }
}
~~~

Ví dụ chỉ minh họa **cấu trúc vòng điều khiển**; kết quả `catch` cần được giữ trong hệ thống lưu trạng thái bền vững, không chỉ `print()` ra stdout. Nếu job chết sau khi server ghi nhưng trước khi checkpoint được lưu, lần chạy lại phải **reconcile/idempotent** thay vì giả định batch chưa thực hiện.

### 14.6. Bước 6 — Quan sát và đối soát

Hãy đo ít nhất:

| Chỉ số | Câu hỏi |
|---|---|
| `insertedCount` / `upsertedCount` | Bao nhiêu document đã tạo mới? |
| `matchedCount` / `modifiedCount` | Bao nhiêu document khớp, bao nhiêu thực sự thay đổi? |
| `deletedCount` | Có đúng số xóa được policy cho phép không? |
| Bulk error rate theo code | Có duplicate key/validation hoặc lỗi môi trường không? |
| p95 latency mỗi batch | Batch có vượt giới hạn SLO? |
| Replication lag / disk / CPU | Batch có gây áp lực cluster? |
| Write conflicts / lock waits | Có hot document hay contention bất thường? |
| Số lượng invalid/missing sau import | Có sai lệch schema hoặc bỏ sót? |
| Job checkpoint + reconcile count | Có operation bị mất/ghi trùng sau lỗi? |

Đối với xóa dữ liệu, lưu audit phù hợp yêu cầu pháp lý và nghiệp vụ. Không dựa vào `deletedCount` để chứng minh **đúng đối tượng** đã bị xóa; cần danh sách ID hoặc bằng chứng truy vấn phù hợp.

## 15. Những nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “bulkWrite là một transaction.” | Không. Một bulk thường có thể thành công một phần. |
| “ordered true thì lỗi sẽ rollback các bước trước.” | Không. Ordered dừng phần sau, không hoàn tác phần trước. |
| “unordered false chỉ là ordered nhưng nhanh hơn.” | Unordered có thể **đổi thứ tự**; dependency có thể sai. |
| “bulkWrite luôn chạy trong một command duy nhất.” | Driver có thể chia thành nhiều server batches. |
| “insertOne trong bulk chỉ cần document, không cần key document.” | Hình dạng là `{insertOne:{document:{...}}}`. |
| “updateOne và updateMany chỉ khác số lượng dự kiến.” | Một sửa tối đa một document; một sửa **tất cả document khớp**. |
| “replaceOne giữ lại những field không có trong replacement.” | Không, replace thay toàn bộ nội dung ngoài quy tắc `_id`. |
| “deleteOne chọn một document ngẫu nhiên luôn ổn.” | Cần filter định danh cụ thể để xóa đúng. |
| “deleteMany với filter trống không nguy hiểm.” | `{}` có thể xóa toàn collection. |
| “matchedCount luôn bằng modifiedCount.” | Update no-op vẫn match nhưng không sửa. |
| “upsertedCount là insertedCount.” | Upsert được đếm riêng với insertOne. |
| “upsert true biến updateMany thành insert nhiều bản ghi mới.” | Nếu không match, updateMany upsert thường tạo **một** document. |
| “Không thấy exception thì cần retry cả bulk để chắc chắn.” | Replay `$inc` có thể tăng hai lần; phải hiểu acknowledgment/retry policy. |
| “retryWrites=true làm mọi bulk có updateMany retry tự động.” | Multi-document writes không thuộc nhóm retryable writes bình thường. |
| “write concern majority đồng nghĩa atomicity toàn bulk.” | Write concern là mức xác nhận ghi, không tự tạo transaction. |
| “Mongo.bulkWrite và collection.bulkWrite dùng cùng write model.” | Hình dạng API và phạm vi khác nhau. |
| “bypassDocumentValidation bỏ qua unique index.” | Không; các ràng buộc khác vẫn hoạt động. |
| “Thấy lỗi ở operation index 5 thì 0–4 đều thành công.” | Với unordered không có bảo đảm thứ tự; phải đọc result/đối soát. |
| “Một bulk to nhất sẽ nhanh nhất.” | Batch lớn tăng overhead xử lý lỗi, memory và latency; cần đo workload. |
| “Write concern error nghĩa là chưa ghi gì.” | Không chắc. Ghi có thể đã áp dụng nhưng chưa đạt mức xác nhận yêu cầu. |

## 16. Câu hỏi thường gặp

**Q1. Có thể trộn insert, update, replace và delete trong một bulk không?**  
Có. `db.collection.bulkWrite()` nhận array các model cho sáu loại thao tác trên **cùng một collection**.

**Q2. `bulkWrite()` khác `insertMany()` thế nào?**  
`insertMany()` chỉ để **insert nhiều document**; `bulkWrite()` cho phép kết hợp **thêm, sửa, thay, xóa**. Nếu chỉ cần insert nhiều document, `insertMany()` thường đơn giản hơn.

**Q3. Một thao tác trong bulk thất bại, các thao tác khác có chạy không?**  
Với `ordered: true`, write error thường dừng những thao tác kế tiếp. Với `ordered: false`, những thao tác độc lập khác được tiếp tục thử. Cả hai đều không tự rollback các ghi đã thành công ngoài transaction.

**Q4. Có thể thay `updateOne` bằng `replaceOne` không?**  
Chỉ khi muốn **thay toàn bộ document** và đã chuẩn bị đủ các field cần giữ. Nếu chỉ muốn sửa một vài field, dùng update operators.

**Q5. `deleteMany` có xóa nguyên tử tất cả document không?**  
Không, mỗi document được xóa theo ngữ nghĩa thao tác và toàn nhóm không tự có atomicity. Nếu nghiệp vụ yêu cầu transaction, phải thiết kế riêng và tính tới chi phí.

**Q6. Dùng unordered có an toàn cho hai update cùng `_id` không?**  
Chỉ khi các update **giao hoán/không phụ thuộc thứ tự** và đã được kiểm tra. Hai `$set` khác nhau lên cùng một field có thể cho kết quả cuối khác nhau tùy thứ tự.

**Q7. Vì sao `matchedCount` nhiều hơn `modifiedCount`?**  
Vì document khớp filter nhưng giá trị update trùng giá trị hiện có, nên không có thay đổi. Một document cũng có thể bị match ở **nhiều operation** trong cùng bulk.

**Q8. Có thể bulkWrite nhiều collection trên MongoDB 7.0 không?**  
Không bằng `Mongo.bulkWrite()` đa namespace, vì khả năng này có từ MongoDB 8.0. Trong MongoDB 7.0 có thể gọi `db.collection.bulkWrite()` riêng cho mỗi collection; muốn bảo đảm atomicity nhiều collection cần transaction có hỗ trợ.

**Q9. Nếu client timeout, có nên chạy lại toàn bộ batch?**  
Không tự động. Cần phân loại loại write, tính retryable theo driver/server và đối soát trạng thái thực tế. Với `$inc`/`deleteMany`, replay có thể tạo thêm side effects.

**Q10. BulkWrite có tự giữ thứ tự khi sharded không?**  
`ordered: true` giữ thứ tự logic giữa các operation; `ordered: false` cho phép server xử lý không theo thứ tự. Thực thi vật lý phụ thuộc shard key, routing và driver.

**Q11. Có nên bỏ hết indexes để bulk insert nhanh hơn?**  
Không có quy tắc chung. Indexes tăng chi phí ghi nhưng bảo đảm truy vấn và ràng buộc unique. Nếu import quá lớn, phải đánh giá giải pháp dữ liệu/index theo runbook, không bỏ index bảo vệ bất biến nghiệp vụ chỉ vì muốn tốc độ.

**Q12. BulkWrite giúp chống duplicate key không?**  
Không. Unique index và ID định danh vẫn kiểm tra như các lệnh CRUD độc lập; unordered chỉ cho phép các operation không lỗi tiếp tục, chứ không sửa dữ liệu trùng.

## 17. Bài tập thực hành có đáp án gợi ý

Sử dụng database `bulk_lab` ở các mục trước. Các bài thực hành update/delete cần được thực hiện trên **collection thử nghiệm riêng** hoặc data fixture được tái tạo; các lệnh có tác dụng thay đổi/xóa thật trên collection chỉ định. Không dùng production chỉ để xem kết quả demo.

### Bài 1 — Trộn insert và update một document

Yêu cầu: thêm `_id = "TASK-1"` có `count: 0`, sau đó tăng `count` lên 2 trong **cùng một `bulkWrite`**. Điều kiện là thao tác tăng phải diễn ra sau insert.

**Đáp án:**

~~~javascript
db.getSiblingDB("bulk_lab").taskDemo.bulkWrite([
  {
    insertOne: {
      document: { _id: "TASK-1", count: 0 }
    }
  },
  {
    updateOne: {
      filter: { _id: "TASK-1" },
      update: { $inc: { count: 2 } }
    }
  }
], { ordered: true })
~~~

Kỳ vọng document cuối có `count: 2`. Nếu chọn unordered, không đảm bảo update sẽ chạy sau insert.

### Bài 2 — Replace khác update

Document ban đầu:

~~~javascript
{ _id: "A", name: "An", city: "Hà Nội", tier: "GOLD" }
~~~

Hai operation:

~~~javascript
// Operation X
{ updateOne: {
    filter: { _id: "A" },
    update: { $set: { city: "Đà Nẵng" } }
} }

// Operation Y
{ replaceOne: {
    filter: { _id: "A" },
    replacement: { _id: "A", city: "Đà Nẵng" }
} }
~~~

**Câu hỏi:** kết quả cuối khác nhau thế nào nếu chỉ chạy một trong hai?

**Đáp án:** X giữ `name` và `tier`, chỉ sửa `city`. Y thay toàn bộ document nên sau replace chỉ còn `_id` và `city`.

### Bài 3 — Dừng khi duplicate key

Collection có duy nhất `{_id: "A"}`, bulk:

~~~javascript
[
  { insertOne: { document: { _id: "B" } } },
  { insertOne: { document: { _id: "A" } } },
  { insertOne: { document: { _id: "C" } } }
]
~~~

**Câu hỏi:** kết quả với ordered và unordered?

**Đáp án:**

- `ordered: true`: B được thêm, A lỗi duplicate key, C không được chạy; document A và B tồn tại.
- `ordered: false`: A vẫn lỗi, còn B/C có thể thành công; không nên suy thứ tự thực thi từ vị trí array.
- Cả hai trường hợp, bulk có thể báo lỗi **sau khi đã ghi một phần**.

### Bài 4 — Filter xóa nhiều có an toàn không?

Một job muốn xóa toàn bộ sản phẩm đã archive trước ngày 1/1/2025 nhưng không được xóa sản phẩm đang ở trạng thái `legalHold: true`.

**Đáp án gợi ý:**

~~~javascript
const filter = {
  archived: true,
  archivedAt: { $lt: ISODate("2025-01-01T00:00:00Z") },
  legalHold: false
}

db.getSiblingDB("bulk_lab").products.bulkWrite([
  { deleteMany: { filter } }
])
~~~

Đừng dùng `legalHold: {$ne:true}` nếu document thiếu field `legalHold` **không** được xóa theo policy. Nên preflight bằng `countDocuments(filter)` và lấy mẫu ID trước.

### Bài 5 — Upsert với `$setOnInsert`

Thiết kế operation tạo product mới nếu chưa tồn tại, nhưng **không ghi lại `createdAt`** nếu product đã có.

**Đáp án:**

~~~javascript
db.getSiblingDB("bulk_lab").products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-TASK5" },
      update: {
        $set: { active: true },
        $setOnInsert: {
          sku: "TASK-5",
          createdAt: new Date()
        }
      },
      upsert: true
    }
  }
])
~~~

Nếu không match, insert document mới. Nếu match, chỉ `$set active`; `$setOnInsert` không sửa `createdAt` hiện có.

### Bài 6 — `matchedCount` và `modifiedCount`

Giả sử `P-100` đã có `status: "ACTIVE"`. Bulk chạy hai lần `updateOne` cùng filter P-100 và cùng `$set: {status:"ACTIVE"}`. Kỳ vọng hai bộ đếm nào?

**Đáp án:** `matchedCount = 2` vì cả hai operation match; `modifiedCount = 0` nếu cả hai đều không làm thay đổi field. Một document có thể được match nhiều lần trong cùng bulk.

### Bài 7 — Điều kiện cùng phần tử khi update array

Trong collection `orders` có:

~~~javascript
{
  _id: "O-ARRAY",
  items: [
    { sku: "BK-01", packed: false },
    { sku: "PN-02", packed: false }
  ]
}
~~~

Viết một update model trong bulk chỉ đổi `packed: true` cho item BK-01.

**Đáp án:**

~~~javascript
{
  updateOne: {
    filter: { _id: "O-ARRAY" },
    update: {
      $set: { "items.$[line].packed": true }
    },
    arrayFilters: [
      { "line.sku": "BK-01" }
    ]
  }
}
~~~

Đặt model này trong array của `db.orders.bulkWrite([...])`. `arrayFilters` thuộc **operation update**, không phải `options` chung chứa `ordered`.

### Bài 8 — `updateMany` và upsert

Không có document nào match `{sku:"UNKNOWN"}`. `updateMany` có `upsert:true` sẽ tạo bao nhiêu document?

**Đáp án:** Trong trường hợp không có match, nó có thể tạo **một** document. Upsert không biến một updateMany thành một insertMany.

### Bài 9 — Retry sau network timeout

Bulk có `updateOne` với `$inc:{stock:10}` và `deleteMany`. Client bị timeout không biết kết quả. Có thể gửi lại toàn batch nguyên xi không?

**Đáp án:** Không mặc nhiên an toàn. `$inc` có thể tăng lần nữa nếu request trước đã ghi; `deleteMany` có thể xóa thêm document vừa thỏa filter trong thời gian giữa hai lần gọi. Bulk hỗn hợp chứa multi-document write không được bảo đảm retryable như bulk chỉ có single-document operations. Cần đối soát theo business key/event ID và chỉ replay những thao tác được thiết kế idempotent.

### Bài 10 — Chọn transaction hay bulk độc lập

Một nghiệp vụ phải trừ tồn kho ở `products` và thêm reservation vào `reservations`, hoặc cả hai cùng thành công, hoặc cả hai không được xuất hiện. Gọi hai `bulkWrite` liên tiếp có đạt yêu cầu không?

**Đáp án:** Không. Hai lời gọi không có atomicity chung. Cần transaction trên deployment hỗ trợ hoặc mô hình công việc/compensation phù hợp; MongoDB 8.0 `Mongo.bulkWrite()` đa namespace cũng **không tự thay thế transaction**.

### Bài 11 — Chuyển API collection sang multi-namespace

Viết một `Mongo.bulkWrite()` trên MongoDB 8.0+ để insert `products` và `auditEvents`.

**Đáp án:**

~~~javascript
db.getMongo().bulkWrite([
  {
    namespace: "bulk_lab.products",
    name: "insertOne",
    document: {
      _id: "P-TASK11",
      name: "Sản phẩm 11"
    }
  },
  {
    namespace: "bulk_lab.auditEvents",
    name: "insertOne",
    document: {
      _id: "EV-TASK11",
      productId: "P-TASK11",
      event: "CREATED"
    }
  }
], { ordered: true })
~~~

Khác API collection, mỗi operation có **`namespace` và `name`**. Nếu cần hai insert cùng commit hoặc abort, phải dùng transaction/`Session.bulkWrite()` theo tài liệu.

### Bài 12 — Chia batch và khôi phục lỗi

Một file import có 250.000 operation, mỗi operation cập nhật một product khác nhau. Driver hỗ trợ batching. Hãy đề xuất kế hoạch có khả năng khôi phục.

**Đáp án gợi ý:**

1. Gắn **batchId** và **operationId/business key** cho từng operation; đảm bảo input có thể tái dựng.
2. Chia các nhóm do ứng dụng quản lý, ví dụ **1.000–5.000 operation** mỗi nhóm để dễ theo dõi; đo lại trên tải thật.
3. Dùng `ordered:false` **chỉ khi** các operation độc lập và không phụ thuộc thứ tự.
4. Nếu có lỗi, thu `writeErrors` và kết quả một phần, đối soát database theo ID.
5. Retry có giới hạn những operation chưa đạt trạng thái mong muốn; không replay mù các phép `$inc`.
6. Lưu checkpoint bền vững **sau khi đối soát** rồi mới chuyển sang batch tiếp theo.
7. Theo dõi latency, write conflicts, replication lag, memory và tổng số document thay đổi.

### Bài 13 — Tính đúng đắn với unordered

Cho hai update cùng target P-100:

~~~javascript
[
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { state: "PENDING" } }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { state: "SHIPPED" } }
    }
  }
]
~~~

**Câu hỏi:** có được chạy unordered vì mỗi update chỉ tác động một document không?

**Đáp án:** Không nếu trạng thái cuối phải là `SHIPPED`. Hai thao tác **phụ thuộc thứ tự**; unordered không đảm bảo trình tự. Cần ordered hoặc tốt hơn là cập nhật trạng thái có điều kiện và luật chuyển trạng thái đúng nghiệp vụ.

### Bài 14 — Một operation lỗi validation

Bulk unordered có ba insert, một document sai schema collection, hai document hợp lệ. Có chắc cả batch rollback không?

**Đáp án:** Không. Hai insert hợp lệ có thể vẫn thành công; operation sai schema có thể bị từ chối theo `validationAction`. Exception của bulk cần được phân tích để biết những phần tử thành công/thất bại, không coi cả batch là transaction.

## 18. Bảng lựa chọn nhanh

| Nhu cầu | Lựa chọn gợi ý | Cảnh báo |
|---|---|---|
| Chỉ insert nhiều document, không update/delete | `insertMany()` | Xử lý duplicate và `ordered` như tình huống import. |
| Trộn insert/update/delete trên **một collection** | `db.collection.bulkWrite()` | Không tự atomic toàn batch. |
| Thao tác độc lập, muốn xử lý hết dù có vài lỗi | `bulkWrite(...,{ordered:false})` | Thứ tự không cố định, phải xử lý partial results. |
| Thao tác có dependency theo thứ tự | `bulkWrite(...,{ordered:true})` | Ordered vẫn không rollback khi lỗi. |
| Thay một vài field mà giữ phần còn lại | `updateOne`/`updateMany` | `replaceOne` có thể làm mất field. |
| Đồng bộ “có thì sửa, chưa có thì thêm” | `upsert:true` với unique identity | Xem race và tính idempotent của update. |
| Xóa chính xác một bản ghi | `deleteOne` với filter theo ID | Filter rộng có thể xóa nhầm. |
| Xóa nhóm theo policy | `deleteMany` có preflight/audit | Cân nhắc retention và rollback. |
| Ghi trên nhiều collection/database ở 8.0+ | `Mongo.bulkWrite()` | Operation objects khác API collection; không tự transactional. |
| Cần commit/abort nhiều document cùng nhau | Multi-document transaction | Giới hạn tài nguyên, retry/commit semantics riêng. |
| Migration cực lớn có thể tiếp tục sau lỗi | Nhiều bulk nhỏ + checkpoint/idempotency | Đối soát operation sau partial failures. |

## 19. Tài liệu MongoDB chính thức

Các trang sau thuộc MongoDB Database Manual và driver docs. Khi dùng production, hãy chọn đúng **MongoDB Server version**, `mongosh` version và **driver version**. Các đường dẫn `/docs/manual/` có thể trỏ tới bản hiện hành; dùng `/docs/v7.0/`, `/docs/v8.0/` nếu cần cố định một dòng.

1. [`db.collection.bulkWrite()` — mongosh method](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — cú pháp sáu operation models, `ordered`, `writeConcern`, counters, batching và lỗi.
2. [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/) — tổng quan ordered/unordered, phạm vi collection và tính năng nhiều namespace từ 8.0.
3. [`Mongo.bulkWrite()` — mongosh method](https://www.mongodb.com/docs/manual/reference/method/mongo.bulkwrite/) — hình dạng `namespace`/`name`, `verboseResults` và ví dụ đa collection.
4. [`bulkWrite` Database Command](https://www.mongodb.com/docs/manual/reference/command/bulkwrite/) — cấu trúc raw command `ops`/`nsInfo` từ MongoDB 8.0; không nhầm với helper collection.
5. [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — điều kiện hỗ trợ và giới hạn đối với bulk chứa `updateMany`/`deleteMany`.
6. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity nhiều document, retry transaction và transaction lifecycle.
7. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j` và các mức xác nhận ghi.
8. [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — `maxWriteBatchSize`, giới hạn BSON document và các giới hạn hệ thống.
9. [`db.collection.insertMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/) — khi chỉ cần chèn nhiều document.
10. [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/), [`updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — update operators, upsert, array filters và tính nguyên tử.
11. [`db.collection.replaceOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.replaceOne/) — khác biệt replace và modifier update.
12. [`db.collection.deleteMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/) — phạm vi xóa nhiều và tác động trong concurrent workload.
13. [Bulk Write Operations — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/) — `WriteModel`, `BulkWriteResult`, `MongoBulkWriteException` và driver APIs.
14. [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — khi bulk write phải đáp ứng validator hoặc sử dụng ngoại lệ được cấp quyền.
15. [MongoDB 7.0 — Bulk Write Operations](https://www.mongodb.com/docs/v7.0/core/bulk-write-operations/) và [MongoDB 8.0 — `db.collection.bulkWrite()`](https://www.mongodb.com/docs/v8.0/reference/method/db.collection.bulkWrite/) — ví dụ tra cứu cố định theo dòng phát hành.

**Kết luận:** `bulkWrite` là công cụ **tổ chức và tối ưu việc gửi các thao tác ghi**, không phải cơ chế tự động đảm bảo mọi thay đổi cùng thành công. Thiết kế đúng đòi hỏi chọn chính xác **sáu loại operation**, xác định **phụ thuộc thứ tự**, chuẩn bị cho **partial results**, phân biệt **retryable với idempotent**, và đặt **transaction boundary** ở đúng quy tắc nghiệp vụ. Khi cần xóa/cập nhật nhiều document, một filter đúng cùng khả năng đối soát kết quả quan trọng hơn việc gom thật nhiều lệnh vào một batch.
