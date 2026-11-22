# Gán, xóa và đổi tên trường với $set, $unset và $rename trong MongoDB

## Mục tiêu bài học

Trong MongoDB, dữ liệu được lưu dưới dạng **document BSON** với các trường (field) có thể là giá trị đơn, object lồng nhau hoặc array. Khi cần thay đổi một vài trường của document, ứng dụng thường không nên đọc toàn bộ document, sửa object trong bộ nhớ rồi ghi đè tất cả. MongoDB cung cấp **update operators** để thay đổi chính xác những phần dữ liệu mong muốn.

Ba toán tử được sử dụng nhiều là:

- **`$set`:** gán giá trị cho một trường; nếu đường dẫn hợp lệ nhưng trường chưa tồn tại, MongoDB có thể tạo trường đó.
- **`$unset`:** loại bỏ một trường khỏi document.
- **`$rename`:** đổi tên một trường bằng cách chuyển giá trị từ tên cũ sang tên mới, với những ràng buộc cần chú ý.

Sau bài học, người học có thể:

1. Viết lệnh `updateOne()` và `updateMany()` với ba toán tử trên.
2. Phân biệt cập nhật một field bằng **dot notation** với thay thế toàn bộ một embedded document.
3. Hiểu khác biệt giữa **gán `null`** và **xóa field**.
4. Dùng `$rename` với field cấp cao hoặc field lồng nhau và nhận diện nguy cơ ghi đè field đích.
5. Cập nhật field bên trong phần tử array với các toán tử và cú pháp phù hợp, đồng thời hiểu giới hạn của `$rename` đối với array.
6. Đọc kết quả `matchedCount`, `modifiedCount` và xử lý trường hợp không khớp.
7. Đánh giá ảnh hưởng của cập nhật tới schema validation, index, ứng dụng và dữ liệu lịch sử.
8. Lập một quy trình migration field name có thể chạy lại, kiểm tra được và tránh mất dữ liệu.

> **Ghi nhớ:** `$set` thay **giá trị**, `$unset` bỏ **trường**, `$rename` đổi **tên trường**. Cả ba thao tác đều có thể ảnh hưởng logic truy vấn, validator và index; hãy xem chúng là thay đổi dữ liệu có chủ đích, không chỉ là chỉnh một object JavaScript.

---

## 1. Update document khác replace document ở đâu?

Giả sử collection `customers` có document:

~~~javascript
{
  _id: "CUS-101",
  fullName: "Nguyễn Mai",
  contact: {
    email: "mai@example.test",
    phone: "0900000001"
  },
  profile: {
    city: "Đà Nẵng",
    loyaltyTier: "SILVER"
  },
  status: "ACTIVE",
  tags: ["new", "newsletter"],
  createdAt: ISODate("2026-10-10T08:00:00Z")
}
~~~

Nhu cầu nghiệp vụ: chỉ đổi số điện thoại.

**Cập nhật một field:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      "contact.phone": "0900000099"
    }
  }
);
~~~

Các field khác như `contact.email`, `profile`, `createdAt` vẫn được giữ nguyên.

**Thay thế document** là loại thao tác khác:

~~~javascript
// KHÔNG dùng lệnh này để minh họa thay đổi một field trên dữ liệu thật.
db.customers.replaceOne(
  { _id: "CUS-101" },
  {
    fullName: "Nguyễn Mai",
    contact: { phone: "0900000099" }
  }
);
~~~

Nếu lệnh replace thành công, các field không được đưa vào replacement như `status`, `profile`, `tags` có thể bị mất. Trường `_id` của document được giữ theo quy tắc của thao tác replacement, nhưng những field nghiệp vụ khác không tự được merge lại.

| Thao tác | Ý nghĩa | Nguy cơ |
|---|---|---|
| `updateOne(filter, {$set: {...}})` | Chỉ đặt các field nêu trong toán tử | Đặt nhầm đường dẫn hoặc ghi đè object con |
| `updateOne(filter, {$unset: {...}})` | Bỏ những field nêu trong toán tử | Mất giá trị field nếu không có nguồn phục hồi |
| `updateOne(filter, {$rename: {...}})` | Chuyển tên field | Ghi đè field đích hoặc làm ứng dụng cũ không còn đọc được |
| `replaceOne(filter, replacement)` | Thay cả document theo replacement | Mất các field không được nêu trong replacement |

**Quy tắc thực hành:** Một API PATCH thường thích hợp với update operators; một thao tác thay toàn bộ representation cần quy trình chặt chẽ hơn để tránh làm mất dữ liệu.

### 1.1. Khung lệnh cập nhật

Trong **mongosh**:

~~~javascript
db.collectionName.updateOne(
  { /* điều kiện chọn document */ },
  {
    $set: {
      fieldA: "value"
    },
    $unset: {
      oldField: ""
    },
    $rename: {
      oldName: "newName"
    }
  }
);
~~~

Đây là khung cấu trúc minh họa; trong thao tác thật, những đường dẫn nằm trong nhiều toán tử **không được xung đột** với nhau. Ví dụ không nên đồng thời đặt và xóa chính field `fieldA`, hoặc vừa đặt cả `profile` vừa cập nhật `profile.city` trong cùng update document.

Các hàm thường dùng:

| Hàm | Phạm vi |
|---|---|
| `updateOne(filter, update, options)` | Cập nhật tối đa một document khớp |
| `updateMany(filter, update, options)` | Cập nhật các document khớp; từng document được cập nhật nguyên tử, không phải cả tập một cách nguyên tử |
| `findOneAndUpdate(filter, update, options)` | Tìm một document và cập nhật, có thể trả version trước/sau theo options |
| `bulkWrite([...])` | Gom nhiều operation; vẫn phải hiểu tính nguyên tử và lỗi từng operation |

Các ví dụ tiếp theo dùng chủ yếu `updateOne()` để thấy rõ tác động trên một document.

---

## 2. Chuẩn bị dữ liệu thực hành

Sử dụng một MongoDB instance hoặc replica set **dành riêng cho lab**. Các lệnh tạo và chỉnh sửa document, nên không chạy trên database production.

Trong mongosh:

~~~javascript
use update_fields_lab

db.customers.insertMany([
  {
    _id: "CUS-101",
    fullName: "Nguyễn Mai",
    legacyName: "Nguyen Mai",
    contact: {
      email: "mai@example.test",
      phone: "0900000001"
    },
    profile: {
      city: "Đà Nẵng",
      loyaltyTier: "SILVER"
    },
    status: "ACTIVE",
    tags: ["new", "newsletter"],
    createdAt: ISODate("2026-10-10T08:00:00Z")
  },
  {
    _id: "CUS-102",
    fullName: "Trần Bình",
    legacyName: "Tran Binh",
    contact: {
      email: "binh@example.test"
    },
    profile: {
      city: "Hà Nội",
      loyaltyTier: "GOLD"
    },
    status: "ACTIVE",
    tags: ["vip"],
    createdAt: ISODate("2026-10-11T08:00:00Z")
  },
  {
    _id: "CUS-103",
    fullName: "Lê Chi",
    contact: {
      email: null,
      phone: "0900000003"
    },
    status: "INACTIVE",
    tags: [],
    createdAt: ISODate("2026-10-12T08:00:00Z")
  }
]);
~~~

Kiểm tra:

~~~javascript
db.customers.find().sort({ _id: 1 });
~~~

Các trường hợp được tạo có chủ đích:

- `CUS-101` có cả `contact.email` và `contact.phone`.
- `CUS-102` có `contact.email` nhưng chưa có `contact.phone`.
- `CUS-103` có `contact.email: null`, không có `profile` và `legacyName`.

Sự khác nhau giữa **field bị thiếu** và **field tồn tại với giá trị `null`** sẽ quan trọng khi dùng `$unset`.

---

## 3. `$set`: gán giá trị hoặc tạo trường

### 3.1. Cú pháp

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "VERIFIED"
    }
  }
);
~~~

Sau lệnh, `status` của `CUS-101` trở thành `"VERIFIED"`; những field khác không bị thay đổi chỉ vì chúng không được nhắc tới.

`$set` có hai hành vi chính:

1. Nếu field tồn tại và đường dẫn hợp lệ, **thay giá trị**.
2. Nếu field chưa tồn tại và đường dẫn có thể được tạo hợp lệ, **tạo field rồi gán giá trị**.

Ví dụ `CUS-102` chưa có `contact.phone`:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $set: {
      "contact.phone": "0900000002"
    }
  }
);
~~~

Sau đó:

~~~javascript
db.customers.findOne(
  { _id: "CUS-102" },
  { contact: 1 }
);
~~~

Kết quả minh họa:

~~~javascript
{
  _id: "CUS-102",
  contact: {
    email: "binh@example.test",
    phone: "0900000002"
  }
}
~~~

### 3.2. Gán nhiều trường trong một update

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "ACTIVE",
      "contact.phone": "0911111111",
      "profile.loyaltyTier": "GOLD",
      updatedAt: new Date()
    }
  }
);
~~~

MongoDB áp dụng update trên **một document** theo cơ chế nguyên tử của một thao tác ghi. Các field được nêu có thể được cập nhật cùng nhau mà ứng dụng khác không quan sát trạng thái “nửa update” của cùng document.

Điều này không có nghĩa một lệnh `updateMany()` cập nhật hàng nghìn document là một transaction nguyên tử toàn bộ. Mỗi document riêng lẻ được cập nhật nguyên tử, còn các document khác có thể được quan sát trong quá trình chạy batch.

### 3.3. Tạo object lồng nhau khi parent chưa có

`CUS-103` chưa có `profile`. Lệnh:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-103" },
  {
    $set: {
      "profile.city": "Huế",
      "profile.loyaltyTier": "BRONZE"
    }
  }
);
~~~

có thể tạo object `profile` và các field con:

~~~javascript
{
  profile: {
    city: "Huế",
    loyaltyTier: "BRONZE"
  }
}
~~~

**Điều kiện:** Đường dẫn phải có thể tạo. Nếu `profile` đã chứa một giá trị scalar không tương thích, ví dụ:

~~~javascript
{ _id: "CUS-BAD", profile: "unknown" }
~~~

thì một update theo đường dẫn `"profile.city"` không thể tự động coi chuỗi `"unknown"` là object để thêm field; thao tác có thể thất bại do đường dẫn không hợp lệ. Cần migration kiểu dữ liệu trước khi đặt field con.

### 3.4. Dot notation khác thay thế cả embedded document

**Cập nhật riêng field con:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      "contact.email": "new.mai@example.test"
    }
  }
);
~~~

Sau lệnh, `contact.phone` vẫn còn.

**Đặt lại toàn bộ object con:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      contact: {
        email: "new.mai@example.test"
      }
    }
  }
);
~~~

Trong trường hợp thứ hai, **giá trị của toàn bộ `contact` bị thay bằng object mới**; `contact.phone` không còn vì object gán mới không chứa field này.

| Cách dùng | Tác động |
|---|---|
| `$set: {"contact.email": value}` | Chỉnh field `email` bên trong `contact` |
| `$set: {contact: {email: value}}` | Thay giá trị toàn bộ field `contact` bằng object mới |

Đây là một trong những lỗi phổ biến nhất khi cập nhật embedded document.

### 3.5. `$set` với giá trị `null`

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $set: {
      "contact.email": null
    }
  }
);
~~~

Lệnh này **không xóa** field `contact.email`. Nó giữ field tồn tại và đặt giá trị BSON null.

MongoDB có thể phân biệt hai trạng thái:

~~~javascript
// Tìm document có field contact.email tồn tại
db.customers.find({
  "contact.email": { $exists: true }
});

// Tìm document thiếu field contact.email
db.customers.find({
  "contact.email": { $exists: false }
});

// Tìm field có giá trị BSON null thực sự
db.customers.find({
  "contact.email": { $type: "null" }
});
~~~

Chú ý truy vấn bình thường:

~~~javascript
db.customers.find({
  "contact.email": null
});
~~~

thường **khớp cả document có field bằng null và document thiếu field**, do ngữ nghĩa truy vấn equality với null của MongoDB. Nếu nghiệp vụ phải phân biệt “chưa có giá trị” và “field không tồn tại”, hãy dùng `$exists` hoặc `$type` phù hợp.

### 3.6. `$set` trên array

Có thể thay toàn bộ một array:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      tags: ["verified", "priority"]
    }
  }
);
~~~

Lúc này array cũ được thay bằng array mới. Nếu mục đích là **thêm phần tử** thay vì thay cả mảng, các toán tử như `$push` hoặc `$addToSet` phù hợp hơn.

Có thể cập nhật theo vị trí của phần tử mảng nếu cấu trúc dữ liệu, filter và toán tử hỗ trợ. Tuy nhiên, cần thận trọng với index vị trí: khi mảng thay đổi đồng thời, phần tử ở vị trí số N có thể không còn là phần tử nghiệp vụ bạn định sửa.

### 3.7. Tạo field có thời gian cập nhật

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "ACTIVE",
      updatedAt: new Date()
    }
  }
);
~~~

`new Date()` trong mongosh được tính ở phía client và gửi như một BSON Date. Nếu muốn đặt ngày giờ theo clock của server, MongoDB có toán tử `$currentDate`:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: { status: "ACTIVE" },
    $currentDate: { updatedAt: true }
  }
);
~~~

`$currentDate` không phải trọng tâm bài học nhưng minh họa cách kết hợp những update operators khác nhau mà không xung đột trên cùng field.

### 3.8. `$set` không thay thế `$inc` và kiểm tra tính đồng thời

Ví dụ tăng số điểm:

~~~javascript
// Cách dễ gặp race condition nếu đọc trước rồi ghi lại giá trị
// const oldPoints = db.customers.findOne({ _id: "CUS-101" }).points;
// db.customers.updateOne(..., { $set: { points: oldPoints + 1 } });
~~~

Khi có nhiều writer, cách “đọc rồi `$set`” có thể mất cập nhật. Với phép tăng/giảm số học, `$inc` thường hợp lý hơn:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  { $inc: { points: 1 } }
);
~~~

Nếu ứng dụng cần chỉ chuyển trạng thái khi trạng thái hiện tại đúng, đặt điều kiện trong **filter**:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    status: "ACTIVE"
  },
  {
    $set: { status: "SUSPENDED" }
  }
);
~~~

Khi không khớp, `matchedCount` bằng 0; đó có thể là dấu hiệu trạng thái đã bị thay đổi trước đó.

---

## 4. `$unset`: xóa trường khỏi document

### 4.1. Cú pháp và giá trị phía bên phải

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $unset: {
      legacyName: ""
    }
  }
);
~~~

Sau lệnh, field `legacyName` không còn trong document.

Giá trị của key trong `$unset` là giá trị cú pháp và **không quyết định field được đặt thành giá trị gì**. Người ta thường sử dụng chuỗi rỗng `""` hoặc `1`:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $unset: {
      legacyName: 1
    }
  }
);
~~~

Hai cách đều có ý nghĩa **xóa field**, không phải gán chuỗi rỗng hay gán số 1.

### 4.2. Xóa nhiều field cùng lúc

~~~javascript
db.customers.updateOne(
  { _id: "CUS-102" },
  {
    $unset: {
      "contact.phone": "",
      "profile.loyaltyTier": ""
    }
  }
);
~~~

Chỉ các field được nêu bị loại bỏ. Object cha còn tồn tại nếu nó có những field khác; không nên mặc định MongoDB dọn sạch mọi parent object trống theo một quy tắc nghiệp vụ riêng.

### 4.3. `$unset` không giống `$set: {field: null}`

So sánh trước và sau:

| Trước | Lệnh | Sau |
|---|---|---|
| `{email:"a@example.test"}` | `$set: {email:null}` | `{email:null}` |
| `{email:"a@example.test"}` | `$unset: {email:""}` | `{}` |
| `{}` | `$unset: {email:""}` | `{}` |
| `{email:null}` | `$unset: {email:""}` | `{}` |

Tác động đến truy vấn:

~~~javascript
// Trả document khi field tồn tại, kể cả khi có giá trị null
db.customers.find({
  "contact.email": { $exists: true }
});

// Trả document khi field không tồn tại
db.customers.find({
  "contact.email": { $exists: false }
});
~~~

Về thiết kế schema:

- **`null`** có thể nghĩa là “field được định nghĩa nhưng chưa có giá trị”.
- **Thiếu field** có thể nghĩa là “field không áp dụng”, “phiên bản schema cũ”, hoặc “đã bị xóa”.

Ý nghĩa này cần được thống nhất giữa database và ứng dụng. Không có câu trả lời đúng cho mọi nghiệp vụ.

### 4.4. Xóa một phần field lồng nhau

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $unset: {
      "contact.phone": ""
    }
  }
);
~~~

Nếu trước đó `contact` là:

~~~javascript
{
  email: "mai@example.test",
  phone: "0900000001"
}
~~~

thì sau lệnh nó trở thành:

~~~javascript
{
  email: "mai@example.test"
}
~~~

Không được viết:

~~~javascript
// Xóa toàn bộ contact, không chỉ phone
db.customers.updateOne(
  { _id: "CUS-101" },
  { $unset: { contact: "" } }
);
~~~

trừ khi nghiệp vụ thực sự muốn xóa **cả object `contact`**.

### 4.5. `$unset` trên array: khác với loại bỏ phần tử

Giả sử collection `orders` có:

~~~javascript
{
  _id: "ORD-101",
  items: [
    { sku: "A", quantity: 1, temporaryNote: "promo" },
    { sku: "B", quantity: 2, temporaryNote: "legacy" }
  ]
}
~~~

Nếu mục đích là **bỏ field `temporaryNote` khỏi một item**, có thể dùng positional filtered update:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $unset: {
      "items.$[line].temporaryNote": ""
    }
  },
  {
    arrayFilters: [
      { "line.sku": "B" }
    ]
  }
);
~~~

Kết quả: item có `sku: "B"` vẫn tồn tại, nhưng không còn field `temporaryNote`.

Ngược lại, `$unset` trên **chính phần tử của array** không có nghĩa là rút phần tử ra rồi dồn mảng lại. Với positional `$`, thao tác unset một phần tử mảng đặt vị trí đó thành `null` để giữ vị trí mảng.

Ví dụ minh họa ý nghĩa:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", "items.sku": "B" },
  {
    $unset: { "items.$": "" }
  }
);
~~~

Kết quả mảng có thể có phần tử `null` ở vị trí tương ứng. Nếu cần **xóa hẳn phần tử khỏi array**, sử dụng `$pull` với điều kiện phù hợp:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $pull: {
      items: { sku: "B" }
    }
  }
);
~~~

**Ghi nhớ:** `$unset` bỏ field; `$pull` loại phần tử mảng phù hợp. Chúng không thay thế nhau.

### 4.6. Nếu field không tồn tại thì sao?

Nếu trường được nêu trong `$unset` không tồn tại, thao tác không tạo field mới và không báo lỗi chỉ vì field đó vắng mặt.

~~~javascript
db.customers.updateOne(
  { _id: "CUS-103" },
  {
    $unset: {
      thisFieldNeverExisted: ""
    }
  }
);
~~~

Nếu filter tìm được document, `matchedCount` có thể là 1 nhưng `modifiedCount` là 0 vì thực tế không có thay đổi dữ liệu.

Tính chất này thường giúp một migration dọn field cũ có thể chạy lặp lại, nhưng vẫn phải kiểm tra các điều kiện khác như validator, index và số document phù hợp.

### 4.7. Không xóa các field cấu trúc mà chưa đánh giá ràng buộc

Không thể dùng `$unset` để loại bỏ trường `_id` bắt buộc. Với một collection có JSON Schema validation yêu cầu field `email`, xóa email có thể bị từ chối khi validation đang bật ở mức chặn lỗi.

Ví dụ collection có rule:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["email"]
  }
}
~~~

thì:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $unset: { email: "" }
  }
);
~~~

có thể bị chặn bởi validator nếu làm document không hợp lệ. Một thay đổi schema cần đi kèm thay đổi validator và ứng dụng, không chỉ chạy một update.

---

## 5. `$rename`: đổi tên một field

### 5.1. Cú pháp

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

Nếu document ban đầu có:

~~~javascript
{
  legacyName: "Nguyen Mai"
}
~~~

sau lệnh có:

~~~javascript
{
  displayNameLegacy: "Nguyen Mai"
}
~~~

Giá trị của field cũ được chuyển sang tên mới. Trường `legacyName` không còn.

**Điểm cần phân biệt:** `$rename` đổi **tên field trong document**, không đổi tên collection. Để đổi tên collection là một thao tác khác, như `renameCollection`, có phạm vi và ràng buộc riêng.

### 5.2. Đổi tên field lồng nhau

Ví dụ document có:

~~~javascript
{
  _id: "CUS-201",
  contact: {
    telephone: "0900000009",
    email: "example@example.test"
  }
}
~~~

Đổi `contact.telephone` thành `contact.phone`:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-201" },
  {
    $rename: {
      "contact.telephone": "contact.phone"
    }
  }
);
~~~

MongoDB hỗ trợ các đường dẫn field lồng nhau phù hợp với `$rename`, miễn không vi phạm ràng buộc kiểu dữ liệu và đường dẫn.

### 5.3. Nguy cơ mất dữ liệu khi field đích đã tồn tại

**Cực kỳ quan trọng:** Nếu tên đích đã có giá trị, `$rename` có thể **ghi đè giá trị ở field đích**.

Giả sử:

~~~javascript
{
  _id: "CUS-301",
  oldEmail: "old@example.test",
  email: "current@example.test"
}
~~~

Chạy:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-301" },
  {
    $rename: {
      oldEmail: "email"
    }
  }
);
~~~

sẽ chuyển giá trị từ `oldEmail` sang `email`; giá trị `"current@example.test"` ở đích có thể bị mất.

Vì vậy, **không chạy `$rename` hàng loạt trước khi kiểm tra những document có cả field nguồn và field đích**.

Cách thống kê xung đột:

~~~javascript
db.customers.countDocuments({
  oldEmail: { $exists: true },
  email: { $exists: true }
});
~~~

Cách tìm mẫu:

~~~javascript
db.customers.find(
  {
    oldEmail: { $exists: true },
    email: { $exists: true }
  },
  {
    _id: 1,
    oldEmail: 1,
    email: 1
  }
).limit(20);
~~~

Nếu kết quả khác 0, phải định nghĩa quy tắc nghiệp vụ: ưu tiên field nào, có cần đối chiếu hoặc lưu lại cả hai, hay phải dừng migration để xử lý thủ công.

### 5.4. Nếu field nguồn không tồn tại

Khi field nguồn không có, `$rename` không tự tạo field đích và thường không tạo thay đổi cho document ấy:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-103" },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

Trong dữ liệu lab, `CUS-103` vốn không có `legacyName`. Thao tác này không tạo `displayNameLegacy` chỉ vì một lệnh rename được yêu cầu.

### 5.5. `$rename` không dùng để sửa field trong phần tử array

Giả sử document:

~~~javascript
{
  _id: "ORD-301",
  items: [
    { oldCode: "A", quantity: 1 },
    { oldCode: "B", quantity: 2 }
  ]
}
~~~

Không thể dùng `$rename` kiểu:

~~~javascript
// Không phải cách được hỗ trợ để đổi field bên trong mỗi phần tử array.
db.orders.updateOne(
  { _id: "ORD-301" },
  {
    $rename: {
      "items.oldCode": "items.sku"
    }
  }
);
~~~

Toán tử `$rename` **không hỗ trợ đổi tên field nằm trong array**. Nếu muốn đổi `oldCode` thành `sku` trong mọi item, cần một chiến lược khác: migration ở application, aggregation pipeline update với `$map`/các toán tử biến đổi object được hỗ trợ theo version, hoặc viết lại các phần tử theo logic đã kiểm chứng.

Với array, vẫn có thể dùng `$set` và `$unset` trên **field của phần tử** bằng `arrayFilters`, nhưng đó không đồng nghĩa `$rename` có thể nhận positional path.

### 5.6. `$rename` không bảo toàn vị trí field trong document

Thứ tự field trong một BSON document không phải thứ tự nghiệp vụ của dữ liệu. `$rename` có thể thay đổi vị trí/ordering của các field trong document. Đừng thiết kế API, serializer hoặc logic xử lý dựa vào việc field đổi tên nằm đúng vị trí cũ.

Nếu cần một thứ tự hiển thị, hãy điều khiển ở query projection, application layer hoặc UI chứ không phụ thuộc vào thứ tự vật lý của field trong document.

### 5.7. `$rename` và field name đặc biệt

Dot notation (`"contact.phone"`) thông thường biểu diễn đường dẫn vào embedded document, không phải một field top-level có tên chứa dấu chấm theo nghĩa literal. Một số phiên bản MongoDB cho phép lưu field có ký tự đặc biệt với những hạn chế riêng; các toán tử cập nhật thông thường có thể không truy cập theo cách bạn nghĩ. Nếu schema có tên field chứa dấu `.` hoặc bắt đầu bằng `$`, hãy xem các cơ chế như `$getField`, `$setField` và giới hạn version.

Với thiết kế mới, nên dùng tên field rõ ràng, không chứa ký tự có thể gây mơ hồ khi dùng dot notation.

---

## 6. Bảng so sánh `$set`, `$unset` và `$rename`

| Tiêu chí | `$set` | `$unset` | `$rename` |
|---|---|---|---|
| Mục đích | Gán hoặc thay giá trị | Bỏ field | Đổi tên field |
| Trường nguồn chưa tồn tại | Có thể tạo field đích theo đường dẫn hợp lệ | Không thay đổi | Không thay đổi nếu nguồn vắng |
| Field đích đã tồn tại | Ghi đè giá trị được nêu | Xóa field đó | Có thể ghi đè field đích |
| Đường dẫn lồng nhau | Có, dùng dot notation | Có, dùng dot notation | Có, nếu đường dẫn phù hợp và không nằm trong array |
| Field trong object thuộc phần tử array | Có thể dùng positional/arrayFilters | Có thể dùng positional/arrayFilters | Không hỗ trợ rename field trong array |
| Xóa hẳn một phần tử array | Không; đặt giá trị | Không; unset phần tử có thể để lại `null` | Không |
| Tác động đến index | Index liên quan tới giá trị có thể phải cập nhật | Index liên quan có thể phải cập nhật | Index cũ không tự đổi thành index cho tên mới |
| Tác động schema validator | Giá trị mới phải hợp lệ | Không được xóa field bắt buộc nếu validation chặn | Validator và tên field có thể cần cập nhật |
| Cần lưu ý nhất | Ghi đè object con | Khác gán `null` | Ghi đè field đích và migration |

Ví dụ thao tác trên một document có:

~~~javascript
{
  oldName: "An",
  email: "an@example.test",
  profile: { city: "Huế", phone: "0900000001" }
}
~~~

| Update | Kết quả đáng chú ý |
|---|---|
| `$set: {email:"new@example.test"}` | Email đổi, các field khác giữ |
| `$set: {"profile.city":"Đà Nẵng"}` | Chỉ thành phố đổi, phone giữ |
| `$set: {profile:{city:"Đà Nẵng"}}` | Cả object profile bị thay; phone mất |
| `$unset: {email:""}` | Email không còn |
| `$set: {email:null}` | Email còn với giá trị null |
| `$rename: {oldName:"displayName"}` | Tên field đổi và chuyển giá trị |

---

## 7. Cập nhật nhiều document: `updateMany()` và điều kiện an toàn

### 7.1. Ví dụ gán field mặc định cho document còn thiếu

Giả sử muốn tạo `marketingOptIn: false` **chỉ khi field chưa có**:

~~~javascript
db.customers.updateMany(
  {
    marketingOptIn: { $exists: false }
  },
  {
    $set: {
      marketingOptIn: false
    }
  }
);
~~~

Dùng filter `$exists: false` giúp tránh ghi đè các giá trị đồng ý/không đồng ý đã được lưu trước đó.

Một cách nguy hiểm:

~~~javascript
// Không dùng khi collection có giá trị đã được người dùng lựa chọn.
db.customers.updateMany(
  {},
  {
    $set: {
      marketingOptIn: false
    }
  }
);
~~~

Lệnh này cập nhật **mọi** document khớp filter rỗng, có thể ghi đè cả những giá trị `true` hợp lệ.

### 7.2. Xóa field deprecated trên các document còn có field

~~~javascript
db.customers.updateMany(
  {
    deprecatedFlag: { $exists: true }
  },
  {
    $unset: {
      deprecatedFlag: ""
    }
  }
);
~~~

Tuy nhiên, trước khi xóa thực tế cần bảo đảm ứng dụng, job nền, báo cáo và index không còn sử dụng field này.

### 7.3. Đổi tên hàng loạt khi không có xung đột đích

Ví dụ muốn chuyển `legacyName` sang `displayNameLegacy` mà không ghi đè field mới đã có:

~~~javascript
db.customers.updateMany(
  {
    legacyName: { $exists: true },
    displayNameLegacy: { $exists: false }
  },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

Điều kiện này bảo vệ các document có cả nguồn và đích **trong phạm vi filter và tính nguyên tử của từng update document**. Nhưng chúng vẫn tồn tại sau migration vì chưa được xử lý; cần thống kê và quyết định chính sách riêng cho các trường hợp xung đột.

### 7.4. `updateMany()` không phải transaction nguyên tử cho toàn bộ collection

MongoDB áp dụng tính nguyên tử ở phạm vi **một document** với các update thông thường. Khi `updateMany()` ảnh hưởng nhiều document:

- Mỗi document được cập nhật nguyên tử riêng.
- Các document khác có thể được truy vấn khi migration còn chạy.
- Lệnh có thể dừng do lỗi sau khi một số document đã sửa.
- Việc chạy lại phải xét khả năng idempotent và trạng thái dở dang.
- Nếu cần atomicity xuyên nhiều document, phải xem xét transaction được hỗ trợ và chi phí tương ứng.

Vì thế, “lệnh trả lỗi” không mặc nhiên nghĩa là “không document nào bị thay đổi”.

### 7.5. Filter chính xác là lớp bảo vệ đầu tiên

Trước khi chạy `updateMany()`, hãy:

1. Viết filter theo đúng phạm vi: tenant, loại document, version schema, trạng thái, thời gian.
2. Đếm số document phù hợp bằng `countDocuments(filter)`.
3. Xem vài mẫu bằng `find(filter).limit(...)` với projection phù hợp.
4. Kiểm tra xung đột, required fields và validator.
5. Chạy trong môi trường thử hoặc trên batch nhỏ khi phù hợp.
6. Theo dõi `matchedCount` và `modifiedCount`.
7. Kiểm chứng postcondition sau khi cập nhật.

Không xem lệnh `updateMany({}, ...)` như một thao tác vô hại: filter rỗng thường là phạm vi toàn collection.

---

## 8. Kết quả update: hiểu `matchedCount` và `modifiedCount`

Ví dụ:

~~~javascript
const result = db.customers.updateOne(
  { _id: "CUS-101" },
  {
    $set: {
      status: "ACTIVE"
    }
  }
);

printjson(result);
~~~

Một kết quả có thể gồm:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 0,
  upsertedCount: 0
}
~~~

Diễn giải:

- `acknowledged: true`: thao tác có phản hồi xác nhận theo write concern đã yêu cầu.
- `matchedCount: 1`: filter tìm được một document.
- `modifiedCount: 0`: không có document được thay đổi, ví dụ do `status` đã bằng `"ACTIVE"`.
- `upsertedCount: 0`: không có document mới được tạo bởi upsert.

Những trường thường quan trọng:

| Tình huống | `matchedCount` | `modifiedCount` | Giải thích |
|---|---:|---:|---|
| Chọn đúng document, gán giá trị khác | 1 | 1 | Có cập nhật |
| Chọn đúng document, gán lại cùng giá trị | 1 | 0 | Không phát sinh thay đổi dữ liệu |
| Filter không tìm thấy document | 0 | 0 | Không update; có thể do ID sai hoặc trạng thái đã đổi |
| `$unset` field vốn không tồn tại | 1 | 0 | Không có gì để xóa |
| `$rename` nguồn không tồn tại | 1 | 0 | Không có giá trị cần chuyển |

Kết quả thực tế còn phụ thuộc phiên bản, write concern, các thuộc tính khác trong update và các điều kiện hệ thống. Với unacknowledged writes, không nên dựa vào thống kê kết quả như thể chúng luôn có sẵn.

### 8.1. `upsert: true` có thể tạo document mới

~~~javascript
db.customers.updateOne(
  { _id: "CUS-999" },
  {
    $set: {
      status: "ACTIVE"
    }
  },
  {
    upsert: true
  }
);
~~~

Nếu filter không khớp, MongoDB có thể **insert** document mới. Đây là tính năng hữu ích nhưng phải thận trọng khi dùng cho các API “chỉ sửa dữ liệu đang có”; nếu muốn không tạo document mới thì không bật upsert.

Khi dùng migration tên field, một upsert vô tình có thể tạo document thiếu các field bắt buộc hoặc sai dữ liệu nghiệp vụ. Hãy xác định rõ phạm vi create/update.

---

## 9. Kết hợp nhiều toán tử trong một update

Có thể kết hợp `$set`, `$unset` và `$rename` nếu các field không xung đột.

Giả sử document có:

~~~javascript
{
  _id: "CUS-401",
  oldDisplayName: "Phương",
  oldPhone: "0900000001",
  accountStatus: "ACTIVE",
  legacyFlag: true
}
~~~

Nhu cầu:

- Đổi `oldDisplayName` thành `displayName`.
- Bỏ `legacyFlag`.
- Gán `accountStatus` thành `VERIFIED`.
- Đặt `updatedAt` theo giờ hiện tại.

~~~javascript
db.customers.updateOne(
  { _id: "CUS-401" },
  {
    $rename: {
      oldDisplayName: "displayName"
    },
    $unset: {
      legacyFlag: ""
    },
    $set: {
      accountStatus: "VERIFIED",
      updatedAt: new Date()
    }
  }
);
~~~

Các đường dẫn được thao tác khác nhau nên không xung đột. Nếu `displayName` đã tồn tại, rename có thể ghi đè nó; trước khi chạy phải xác minh trường hợp này.

### 9.1. Những tổ hợp xung đột

Ví dụ không hợp lệ về ý nghĩa, và MongoDB có thể từ chối do **conflicting update paths**:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-401" },
  {
    $set: {
      profile: { city: "Huế" },
      "profile.city": "Hà Nội"
    }
  }
);
~~~

Hai cập nhật cùng chạm vào đường dẫn `profile` và nhánh con `profile.city`.

Tương tự, không nên vừa:

~~~javascript
{
  $set: { status: "ACTIVE" },
  $unset: { status: "" }
}
~~~

trong cùng update.

**Đừng phụ thuộc vào thứ tự viết các operator trong object để giải quyết xung đột.** Hãy chia thành các thao tác hợp lệ hoặc chọn một update strategy rõ ràng.

### 9.2. Khi cần biến đổi dựa trên giá trị hiện tại

Các update operators cổ điển thường nhận giá trị literal. Nếu cần lấy giá trị field cũ, tính toán rồi đặt field mới, có thể dùng **update với aggregation pipeline** ở các MongoDB version hỗ trợ.

Ví dụ muốn gán `normalizedName` từ `fullName` đang tồn tại:

~~~javascript
db.customers.updateMany(
  { fullName: { $type: "string" } },
  [
    {
      $set: {
        normalizedName: { $toLower: "$fullName" }
      }
    }
  ]
);
~~~

**Phân biệt cú pháp:** `$set` ở ví dụ trên là một **aggregation pipeline stage** nhận expression, khác với `$set` update operator trong object update truyền thống. Mặc dù cùng tên, cách diễn giải giá trị là khác.

Ví dụ chuyển field bằng pipeline:

~~~javascript
db.customers.updateMany(
  {
    oldField: { $exists: true },
    newField: { $exists: false }
  },
  [
    {
      $set: {
        newField: "$oldField"
      }
    },
    {
      $unset: "oldField"
    }
  ]
);
~~~

Ở dạng pipeline, `"$oldField"` được hiểu như **đường dẫn tham chiếu tới field** trong expression, không phải chuỗi literal. Với update object `{$set: {newField: "$oldField"}}`, đó lại là **chuỗi literal** `"$oldField"`.

Pipeline là một hướng tốt khi migration cần tính toán, nhưng vẫn cần kiểm tra version, types, validator, các field có thể thiếu và tình huống đích đã tồn tại.

---

## 10. Ảnh hưởng tới schema validation, index và truy vấn

### 10.1. Schema validation

Một collection có thể dùng validator:

~~~javascript
db.createCollection("validated_contacts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["email"],
      properties: {
        email: { bsonType: "string" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Nếu document đang hợp lệ mà bạn xóa field bắt buộc `email` bằng `$unset`, MongoDB có thể từ chối ghi vì document sau update không còn hợp lệ.

Tương tự, đổi tên `email` thành `primaryEmail` nhưng validator vẫn yêu cầu `email` sẽ khiến dữ liệu và validator xung đột.

Khi thay đổi field name production, cần lên kế hoạch cùng lúc cho:

- JSON Schema/validator trong MongoDB.
- Validation phía Java/Spring Boot hoặc driver mapping.
- Query, projection, sort, aggregation, reports.
- Index, partial index filter, TTL index hoặc unique constraints.
- API serializer/deserializer và tài liệu hợp đồng dữ liệu.

### 10.2. Index gắn với đường dẫn field

Giả sử có index:

~~~javascript
db.customers.createIndex(
  { legacyName: 1 },
  { name: "idx_legacy_name" }
);
~~~

Sau migration:

~~~javascript
db.customers.updateMany(
  {
    legacyName: { $exists: true },
    displayNameLegacy: { $exists: false }
  },
  {
    $rename: {
      legacyName: "displayNameLegacy"
    }
  }
);
~~~

**Index `{legacyName:1}` không tự đổi định nghĩa thành index `{displayNameLegacy:1}`.** Các query mới:

~~~javascript
db.customers.find({
  displayNameLegacy: "Nguyen Mai"
});
~~~

cần được đánh giá và có thể cần index trên field mới:

~~~javascript
db.customers.createIndex(
  { displayNameLegacy: 1 },
  { name: "idx_display_name_legacy" }
);
~~~

Chỉ sau khi đảm bảo không còn query hoặc ràng buộc sử dụng index cũ, nhóm mới nên cân nhắc loại index cũ theo quy trình quản trị.

### 10.3. Unique index và field bị thiếu

Một unique index trên field có những quy tắc riêng khi field bị thiếu hoặc bằng null; không thể giả định xóa field bằng `$unset` sẽ luôn thành công trên mọi document. Với một **single-field unique index**, nhiều document cùng thiếu field có thể gây xung đột khóa duy nhất trong các điều kiện nhất định.

Nếu dự định xóa hàng loạt field đang được unique index hoặc partial index sử dụng, phải xem quy tắc uniqueness và điều kiện index trước.

### 10.4. Truy vấn dựa trên field cũ sẽ không tự chuyển

Trước migration:

~~~javascript
db.customers.find({ legacyName: "Nguyen Mai" });
~~~

Sau khi field được đổi thành `displayNameLegacy`, truy vấn trên `legacyName` không còn khớp các document đã chuyển. Điều này ảnh hưởng cả:

- Các API cũ chưa triển khai phiên bản mới.
- Batch jobs và consumer dữ liệu.
- Dashboard, báo cáo và materialized views.
- Change Streams consumers xử lý tên field.
- Object mapping, projection và repository method.

Khi ứng dụng chạy nhiều phiên bản đồng thời, một lệnh rename dữ liệu hàng loạt có thể gây gián đoạn nếu chưa có giai đoạn tương thích.

---

## 11. Migration đổi tên field an toàn trong hệ thống đang chạy

### 11.1. Bối cảnh

Hệ thống đang dùng field `phoneNumber` nhưng muốn chuẩn hóa thành `contact.phone`. Có ba nhóm document:

1. Chỉ có `phoneNumber`.
2. Chỉ có `contact.phone`.
3. Có **cả hai** với giá trị có thể khác nhau.

Nếu chạy:

~~~javascript
db.customers.updateMany(
  {},
  {
    $rename: {
      phoneNumber: "contact.phone"
    }
  }
);
~~~

thì nhóm thứ ba có nguy cơ bị ghi đè giá trị đích. Một migration đúng cần quyết định chính sách xử lý xung đột.

### 11.2. Bước 1 — Đo phạm vi hiện trạng

~~~javascript
const hasOld = db.customers.countDocuments({
  phoneNumber: { $exists: true }
});

const hasNew = db.customers.countDocuments({
  "contact.phone": { $exists: true }
});

const hasBoth = db.customers.countDocuments({
  phoneNumber: { $exists: true },
  "contact.phone": { $exists: true }
});

printjson({ hasOld, hasNew, hasBoth });
~~~

Lấy mẫu dữ liệu xung đột:

~~~javascript
db.customers.find(
  {
    phoneNumber: { $exists: true },
    "contact.phone": { $exists: true }
  },
  {
    _id: 1,
    phoneNumber: 1,
    "contact.phone": 1
  }
).limit(20);
~~~

Không chỉ đếm; cần xem phân bố kiểu field, có object `contact` không, có trường hợp `contact` là scalar không, có dữ liệu `null`, và có thể có string/number khác kiểu hay không.

### 11.3. Bước 2 — Thiết kế tương thích ứng dụng

Một quy trình triển khai có thể là:

~~~text
Giai đoạn A: Ứng dụng mới đọc field mới,
             fallback field cũ nếu cần.
             Việc ghi được chuẩn hóa theo quy tắc đã thống nhất.

Giai đoạn B: Tạo index/validator phù hợp với field mới
             mà không phá khả năng chạy của phiên bản cũ.

Giai đoạn C: Backfill dữ liệu chỉ có field cũ.
             Phân loại xung đột và xử lý theo nghiệp vụ.

Giai đoạn D: Xác nhận tất cả consumer đã chuyển sang field mới,
             ngừng ghi field cũ.

Giai đoạn E: Dọn field cũ và index cũ, siết validator,
             giám sát và giữ kế hoạch rollback.
~~~

Nếu hệ thống dùng nhiều service hoặc rolling deployment, khả năng đọc cả hai field trong giai đoạn chuyển tiếp thường rất quan trọng. Việc dual-write, nếu cần, phải có quy tắc nhất quán để tránh hai field lệch nhau.

### 11.4. Bước 3 — Sao lưu và kế hoạch khôi phục

Trước migration lớn:

- Có bản backup hoặc snapshot phù hợp, đã biết cách restore.
- Ghi lại số lượng document và mốc thời gian.
- Có kế hoạch dừng việc ghi gây xung đột hoặc xử lý ghi đồng thời.
- Kiểm tra ảnh hưởng đến throughput, replication lag và dung lượng.
- Có người sở hữu quyết định rollback và runbook.

**`$rename` không phải một cơ chế versioning/undo**. Nếu ghi đè dữ liệu đích, không thể mặc định dùng một lệnh rename ngược để khôi phục giá trị đã mất.

### 11.5. Bước 4 — Chạy backfill có điều kiện

Ví dụ chuyển những document chỉ có field cũ:

~~~javascript
const filter = {
  phoneNumber: { $exists: true },
  "contact.phone": { $exists: false }
};

db.customers.updateMany(
  filter,
  {
    $rename: {
      phoneNumber: "contact.phone"
    }
  }
);
~~~

Trong thực tế phải bảo đảm đường dẫn `contact` tương thích (không đang là scalar), schema validator cho phép kết quả và ứng dụng đã sẵn sàng.

**Không dùng lệnh này cho các document có đích đã tồn tại.** Chúng phải được xử lý riêng theo chính sách ưu tiên giá trị và kiểm tra dữ liệu.

### 11.6. Bước 5 — Xác minh kết quả

~~~javascript
// Số document vẫn còn field nguồn
db.customers.countDocuments({
  phoneNumber: { $exists: true }
});

// Số document có field đích
db.customers.countDocuments({
  "contact.phone": { $exists: true }
});

// Các document còn cả hai field
db.customers.countDocuments({
  phoneNumber: { $exists: true },
  "contact.phone": { $exists: true }
});
~~~

Đối chiếu thêm bằng application read paths, các sample document, thống kê nghiệp vụ và truy vấn sử dụng index mới.

Không chỉ dựa vào `modifiedCount`. Ví dụ một số document có field nguồn nhưng không thỏa điều kiện do xung đột, nên chưa được migration dù lệnh đã chạy thành công trên các document khác.

### 11.7. Bước 6 — Cleanup có kiểm soát

Khi toàn bộ hệ thống chỉ dùng field mới và các xung đột được xử lý, mới cân nhắc `$unset` field cũ, cập nhật validator và loại index cũ. Giữ đủ thời gian quan sát để phát hiện consumer cũ còn chạy.

Một script migration **idempotent** tốt là script có thể chạy lại mà không ghi đè dữ liệu hợp lệ:

- Filter dựa trên `$exists` hoặc schema version.
- Không ghi đè field mới đã có nếu chưa quyết định quy tắc.
- Ghi log số document phù hợp và sửa.
- Có postcondition rõ ràng.
- Không đánh dấu hoàn thành khi còn trường hợp xung đột chưa xử lý.

---

## 12. Chú ý về concurrency, transaction và write concern

### 12.1. Atomicity trên một document

Một update chứa nhiều field trong một document là nguyên tử. Ví dụ:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    status: "ACTIVE"
  },
  {
    $set: {
      status: "VERIFIED",
      verifiedAt: new Date()
    },
    $unset: {
      legacyFlag: ""
    }
  }
);
~~~

Ứng dụng khác không nhìn thấy trạng thái một nửa cập nhật trên cùng document.

Nhưng không suy ra rằng thao tác có thể khôi phục lịch sử tự động. Nếu đã xóa field và commit, muốn lấy lại giá trị phải dựa vào dữ liệu gốc, audit log/backup hoặc cơ chế ghi nhận lịch sử đã được thiết kế từ trước.

### 12.2. Cập nhật nhiều document và giao dịch

Một `updateMany()` không cung cấp atomicity toàn batch. Nếu nghiệp vụ bắt buộc “tất cả document hoặc không document nào”, có thể cần transaction nhiều document trong topology được hỗ trợ, với chi phí vận hành bổ sung. Đối với migration lớn, transaction rất dài không luôn phù hợp; có thể dùng backfill theo batch nhỏ, trạng thái migration và quy tắc tương thích.

### 12.3. Ghi đồng thời

Trong khi backfill, phiên bản ứng dụng cũ có thể vẫn ghi `phoneNumber`. Điều đó khiến field cũ xuất hiện lại dù backfill vừa xong. Vì vậy, phải có chiến lược triển khai:

- Ngừng ghi tên cũ.
- Hoặc hỗ trợ dual-write có kiểm soát.
- Hoặc cho phép tiếp tục backfill nhiều vòng đến khi không còn writer cũ.

Một điều kiện filter `$exists` bảo vệ từng update khỏi đích hiện có, nhưng không giải quyết toàn bộ quy trình rollout khi các phiên bản ứng dụng ghi khác nhau.

### 12.4. Write concern và kết quả không chắc chắn

Nếu write concern timeout, không được kết luận đơn giản rằng update chắc chắn chưa thực hiện. Thao tác có thể đã được áp dụng nhưng chưa đạt điều kiện xác nhận. Khi retry migration, thiết kế **idempotent** và đọc lại trạng thái thực tế sẽ an toàn hơn việc chỉ dựa vào error message.

---

## 13. Ví dụ với Java Driver và Spring Data MongoDB

### 13.1. MongoDB Java Sync Driver

Với MongoDB Java Driver, có thể tạo update bằng helpers trong `com.mongodb.client.model.Updates`.

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.set;
import static com.mongodb.client.model.Updates.unset;
import static com.mongodb.client.model.Updates.rename;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

MongoCollection<Document> customers =
    database.getCollection("customers");

UpdateResult result = customers.updateOne(
    eq("_id", "CUS-101"),
    combine(
        set("contact.phone", "0900000099"),
        unset("legacyFlag"),
        rename("legacyName", "displayNameLegacy")
    )
);

System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
~~~

Đoạn code giả định `database` đã được tạo từ một `MongoClient` đang kết nối; xử lý credential, connection pool, lỗi, retry và log nằm ở lớp ứng dụng.

**Thận trọng:** Ví dụ kết hợp chỉ phù hợp khi các đường dẫn không xung đột và field đích `displayNameLegacy` không có giá trị cần giữ. Trong thực tế cần đặt filter/phân loại dữ liệu trước khi rename.

### 13.2. Spring Data MongoDB với `MongoTemplate`

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("_id").is("CUS-101")
);

Update update = new Update()
    .set("contact.phone", "0900000099")
    .unset("legacyFlag")
    .rename("legacyName", "displayNameLegacy");

var result = mongoTemplate.updateFirst(
    query,
    update,
    "customers"
);
~~~

Chú ý việc ánh xạ `@Id`, tên property Java và tên field BSON thực tế. MongoTemplate có thể áp dụng mapping theo entity class khi sử dụng các overload tương ứng; đừng mặc định chuỗi field ở Java luôn tương đương schema đang lưu nếu đã cấu hình `@Field` hoặc custom converter.

### 13.3. Dùng PATCH API đúng ngữ nghĩa

Một PATCH request có thể mang ba kiểu thao tác:

~~~json
{
  "set": {
    "contact.phone": "0900000099"
  },
  "unset": [
    "legacyNote"
  ]
}
~~~

Đây là **định dạng API giả định**, không phải một MongoDB command. Server phải xác thực danh sách field được phép sửa, loại giá trị, quyền truy cập và chống sửa những field nhạy cảm như `_id`, tenantId hoặc trạng thái nghiệp vụ không hợp lệ.

**Không chuyển mù quáng input của client thành update document MongoDB.** Kẻ gọi API không đáng tin cậy có thể cố ghi field trái phép, thao tác operator injection hoặc thay đổi field dùng cho phân quyền. Hãy whitelist field, validate data và xây update ở tầng server.

### 13.4. Field rename trong ứng dụng không đồng nghĩa migration database

Đổi tên property Java:

~~~java
private String primaryEmail;
~~~

không tự đổi những field BSON cũ đã lưu trên MongoDB. Có thể dùng annotation mapping để duy trì tương thích tạm thời, nhưng về lâu dài cần quyết định khi nào migration dữ liệu, sửa query, index và validator.

---

## 14. Các lỗi thường gặp và cách xử lý

### Lỗi A — Cập nhật nested object nhưng mất các field con

**Dấu hiệu:** Sau `$set: {contact: {email: ...}}`, field `contact.phone` biến mất.

**Nguyên nhân:** Đã thay toàn bộ object `contact` thay vì chỉ đổi field `contact.email`.

**Cách làm đúng:**

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  { $set: { "contact.email": "new@example.test" } }
);
~~~

### Lỗi B — Tưởng `$set: {email: null}` là xóa email

**Dấu hiệu:** `$exists: true` vẫn trả document.

**Nguyên nhân:** Field vẫn tồn tại với giá trị null.

**Cách làm đúng:** Dùng `$unset: {email: ""}` khi nghiệp vụ thực sự muốn bỏ field.

### Lỗi C — Xóa phần tử array bằng `$unset` và thấy `null`

**Dấu hiệu:** Array vẫn có cùng độ dài, nhưng phần tử thành null.

**Nguyên nhân:** `$unset` không phải toán tử loại phần tử khỏi array.

**Cách làm đúng:** `$pull` với điều kiện nghiệp vụ phù hợp, hoặc cập nhật array theo chiến lược khác.

### Lỗi D — `$rename` ghi đè field đích

**Dấu hiệu:** Giá trị field mới trước đó không còn.

**Nguyên nhân:** Đã rename mà không kiểm tra document có cả nguồn và đích.

**Cách làm đúng:** Truy vấn xung đột, chốt chính sách ưu tiên, lọc những document chỉ có nguồn và không có đích, lưu backup trước migration.

### Lỗi E — Dùng `$rename` với field bên trong array

**Dấu hiệu:** Rename không được hỗ trợ hoặc kết quả không như ý.

**Nguyên nhân:** `$rename` không hỗ trợ rename field trong các phần tử array.

**Cách làm đúng:** Dùng migration riêng với application hoặc aggregation pipeline phù hợp phiên bản, có kiểm chứng dữ liệu.

### Lỗi F — Thao tác không sửa document nào

**Dấu hiệu:** `matchedCount: 0` hoặc `modifiedCount: 0`.

**Nguyên nhân có thể:**

- Filter sai `_id` hoặc sai kiểu BSON.
- Điều kiện trạng thái không còn đúng.
- Field vốn đã mang giá trị mới.
- Field cần unset/rename không tồn tại.

**Cách làm đúng:** Đọc lại filter và trạng thái thực tế, không tự động nới filter thành `{}` chỉ để thấy một document được sửa.

### Lỗi G — Đường dẫn con không hợp lệ

**Dấu hiệu:** `$set: {"profile.city":"Huế"}` lỗi.

**Nguyên nhân có thể:** `profile` đang là scalar thay vì object. MongoDB không thể coi một string là embedded document để thêm field con.

**Cách làm đúng:** Phân loại dữ liệu lệch schema và migrate kiểu trước khi update.

### Lỗi H — Không đổi index và validator sau rename

**Dấu hiệu:** Query tên mới chậm hoặc update bị từ chối.

**Nguyên nhân:** Index và validator vẫn dùng tên field cũ.

**Cách làm đúng:** Xem field rename là thay đổi schema, triển khai index/validator và consumer tương ứng.

### Lỗi I — `updateMany()` dừng giữa chừng

**Dấu hiệu:** Một phần document đã sửa, phần còn lại vẫn có field cũ.

**Nguyên nhân:** Từng document được update nguyên tử, nhưng toàn bộ batch không nhất thiết nguyên tử.

**Cách làm đúng:** Thiết kế migration idempotent, filter theo trạng thái còn thiếu, kiểm tra postcondition, giới hạn batch và theo dõi lỗi.

### Lỗi J — Client gửi đường dẫn field tùy ý

**Dấu hiệu:** Dữ liệu phân quyền, trạng thái hoặc metadata bị sửa ngoài ý định.

**Nguyên nhân:** Server xây update document trực tiếp từ input không đáng tin.

**Cách làm đúng:** Whitelist field được phép thay đổi, validate theo role và schema; không cho client tùy ý chọn operator hoặc đường dẫn nhạy cảm.

---

## 15. Bảng quyết định: chọn toán tử nào?

| Nhu cầu | Cách chọn | Ví dụ |
|---|---|---|
| Đổi email đang có | `$set` | `{"contact.email":"new@example.test"}` |
| Tạo field mới khi chưa có | `$set` với filter phù hợp | `marketingOptIn: false` cho document thiếu |
| Chỉnh thành phố nhưng giữ street | `$set` với dot notation | `{"address.city":"Huế"}` |
| Thay toàn bộ address một cách có chủ đích | `$set` trên object cha | `{address:{...}}` |
| Xóa số điện thoại | `$unset` | `{"contact.phone":""}` |
| Ghi rõ chưa có số điện thoại nhưng field vẫn tồn tại | `$set` thành `null` | `{"contact.phone":null}` |
| Xóa field cũ đã ngừng sử dụng | `$unset` | `{legacyFlag:""}` |
| Đổi tên field top-level | `$rename` | `{oldName:"newName"}` |
| Đổi tên field lồng trong object | `$rename` với đường dẫn | `{"contact.telephone":"contact.phone"}` |
| Đổi field trong phần tử array | Không dùng `$rename` trực tiếp | Migration array bằng logic phù hợp |
| Loại phần tử array phù hợp điều kiện | `$pull` | `{items:{sku:"B"}}` |
| Tăng bộ đếm nguyên tử | `$inc` | `{points:1}` |
| Thêm phần tử vào array | `$push` / `$addToSet` | `{tags:"vip"}` |
| Tính giá trị mới từ field cũ | Update aggregation pipeline | `$set` stage với expression |

Bảng này giúp chọn toán tử; vẫn cần filter, phân quyền, schema validation và đảm bảo nghiệp vụ trước khi thực hiện.

---

## 16. Bài tập thực hành

### Bài tập 1 — Cập nhật một embedded field

Từ dữ liệu lab, thực hiện:

1. Đổi `contact.phone` của `CUS-101` thành `"0912345678"` bằng `$set`.
2. Xác nhận `contact.email` vẫn giữ nguyên.
3. Thử một thao tác `$set` lên toàn bộ `contact` trong database thử nghiệm, quan sát khác biệt.
4. Giải thích vì sao dot notation cần thiết nếu chỉ đổi một field con.

### Bài tập 2 — Phân biệt null và missing

Với `CUS-103`:

1. Tìm theo `"contact.email": null`.
2. Tìm theo `"contact.email": {$exists:true}`.
3. Chạy `$unset` để xóa `contact.email`.
4. Chạy lại hai truy vấn và thêm `$type:"null"`.
5. Giải thích sự khác biệt giữa truy vấn equality null, tồn tại field và giá trị BSON null.

### Bài tập 3 — Đổi tên trường có xung đột

Tạo trong collection lab:

~~~javascript
db.migration_cases.insertMany([
  { _id: 1, oldLabel: "A" },
  { _id: 2, newLabel: "B" },
  { _id: 3, oldLabel: "C", newLabel: "D" },
  { _id: 4, oldLabel: null }
]);
~~~

Hãy:

1. Đếm document có field `oldLabel`.
2. Đếm document có cả `oldLabel` và `newLabel`.
3. Viết filter chỉ chọn document có nguồn và chưa có đích.
4. Dùng `$rename` với filter đó.
5. Xác minh document `_id: 3` không bị mất `newLabel: "D"`.
6. Thảo luận cách xử lý xung đột của document 3.

### Bài tập 4 — Xóa field của phần tử array

Tạo:

~~~javascript
db.orders.insertOne({
  _id: "ORD-501",
  items: [
    { sku: "A", quantity: 1, oldNote: "x" },
    { sku: "B", quantity: 2, oldNote: "y" }
  ]
});
~~~

Yêu cầu:

- Xóa `oldNote` chỉ ở item có `sku: "B"` mà giữ item.
- So sánh với thao tác `$unset` trên nguyên phần tử array.
- Giải thích khi nào dùng `$pull`.

### Bài tập 5 — Cập nhật có điều kiện

Chỉ đổi `status` từ `ACTIVE` thành `SUSPENDED` khi trạng thái hiện tại đúng. Viết `updateOne` có filter theo cả `_id` và `status`. Chạy lại lệnh lần thứ hai; giải thích vì sao `matchedCount` có thể thay đổi.

### Bài tập 6 — Migration tên field production

Một collection có 2 triệu document đang chứa `phoneNumber`; một số document đã có `contact.phone`. Ứng dụng triển khai nhiều instance và có báo cáo vẫn đọc `phoneNumber`.

Hãy thiết kế:

1. Kiểm kê dữ liệu cũ/mới/xung đột.
2. Cách triển khai ứng dụng tương thích.
3. Index và validator cần thay đổi.
4. Lệnh backfill chỉ cho document không xung đột.
5. Cơ chế kiểm tra tiến độ và xử lý lỗi giữa batch.
6. Điều kiện cho phép bỏ field cũ.
7. Kế hoạch backup/rollback nếu phát hiện giá trị sai.

### Bài tập 7 — Java API PATCH an toàn

Giả sử API cho phép sửa `contact.phone`, `profile.city` và xóa `legacyNote`, nhưng không cho sửa `_id`, `tenantId` hoặc `status`.

Hãy viết pseudo-code hoặc Java code:

- Chỉ chấp nhận field hợp lệ.
- Validate kiểu dữ liệu và quyền user.
- Xây `Updates.combine(set(...), unset(...))` từ field đã qua whitelist.
- Kiểm tra `matchedCount` và `modifiedCount`.
- Không cho request tự cung cấp một MongoDB update document tùy ý.

---

## 17. Câu hỏi ôn tập

1. Vì sao `updateOne()` với `$set` khác `replaceOne()`?
2. Khi nào `$set` tạo field mới? Khi nào dot notation gặp lỗi?
3. Khác biệt giữa `$set: {"contact.phone": "..."}` và `$set: {contact: {phone: "..."}}`?
4. Vì sao `$set: {email:null}` không giống `$unset: {email:""}`?
5. Khi nào truy vấn `{email:null}` khớp document thiếu email?
6. `$unset` làm gì nếu field không tồn tại?
7. Vì sao `$unset` trên một phần tử array có thể để lại `null`?
8. Toán tử nào thích hợp để xóa hẳn phần tử khỏi array?
9. `$rename` làm gì nếu field đích đã tồn tại?
10. `$rename` có hỗ trợ đổi tên field nằm trong array không?
11. Vì sao đổi tên field phải đi kèm migration index và validator?
12. `matchedCount` khác `modifiedCount` như thế nào?
13. Một lệnh `updateMany()` có nguyên tử trên tất cả document không?
14. Vì sao `upsert: true` cần được dùng có chủ đích?
15. Điều kiện nào khiến một migration rename có thể chạy lại an toàn?
16. Sự khác nhau giữa `$set` update operator và `$set` aggregation stage là gì?
17. Tại sao ứng dụng không nên nhận trực tiếp MongoDB update operators từ một API request không đáng tin?

## 18. Tổng kết

MongoDB cung cấp ba toán tử thiết yếu để sửa cấu trúc document mà không phải thay thế toàn bộ bản ghi:

- **`$set`** gán hoặc tạo field, hỗ trợ dot notation để chỉnh đúng phần embedded document cần thay đổi.
- **`$unset`** xóa field khỏi document; nó không tương đương gán `null` và không phải công cụ loại bỏ phần tử array.
- **`$rename`** chuyển giá trị sang một tên field mới, nhưng phải kiểm tra field đích, giới hạn array và ảnh hưởng đến query/index/validator.

Trong môi trường học tập, hãy thực hành với `updateOne()` và đọc kết quả để hiểu tác động. Trong hệ thống production, hãy thêm **filter an toàn, phân quyền, schema validation, migration có thể chạy lại, backup và kiểm chứng trạng thái sau cập nhật**. Đặc biệt với `$rename`, hành động đổi tên field là một thay đổi hợp đồng dữ liệu giữa database và tất cả ứng dụng đang sử dụng nó.

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — $set Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/set/)
- [MongoDB Manual — $unset Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/unset/)
- [MongoDB Manual — $rename Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/rename/)
- [MongoDB Manual — db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — Update Documents with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Update Arrays](https://www.mongodb.com/docs/manual/tutorial/use-mql-to-update-an-array/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [Spring Data MongoDB — Updating Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
