# Cập nhật mảng bằng $, $[] và $[identifier] kết hợp arrayFilters trong MongoDB

## 1. Bài toán: sửa đúng phần tử của một document có mảng

Một **document MongoDB** có thể chứa nhiều mảng, bao gồm mảng giá trị đơn giản và mảng các embedded document. Ví dụ, một đơn hàng lưu danh sách dòng hàng trong field **items**:

~~~javascript
{
  _id: "ORD-101",
  customerId: "CUS-01",
  status: "OPEN",
  items: [
    { sku: "PEN-BLUE", qty: 2, state: "NEW" },
    { sku: "NOTE-A5", qty: 1, state: "NEW" },
    { sku: "PEN-BLUE", qty: 5, state: "NEW" }
  ]
}
~~~

Ứng dụng có thể cần:

1. Đánh dấu **dòng hàng đầu tiên có sku = PEN-BLUE** đã được đóng gói.
2. Gắn một thuộc tính cho **tất cả các dòng hàng**.
3. Thay đổi trạng thái của **mọi dòng hàng có qty >= 3 và state = NEW**.
4. Trong từng dòng hàng, sửa **các phần tử của mảng con** theo một điều kiện riêng.

Nếu lấy toàn bộ document về Java, sửa danh sách trong RAM rồi ghi đè toàn bộ mảng, ứng dụng dễ gặp **lost update** khi nhiều request thay đổi cùng đơn hàng. MongoDB cung cấp các **positional update operators** để diễn đạt phần tử cần sửa trực tiếp trong đường dẫn cập nhật:

| Toán tử | Tên thường dùng | Ý nghĩa |
|---|---|---|
| **$** | Positional operator | Cập nhật **phần tử đầu tiên khớp** với điều kiện truy vấn mảng. |
| **$[]** | All positional operator | Cập nhật **mọi phần tử** trong mảng được chỉ định. |
| **$[identifier]** | Filtered positional operator | Cập nhật **mọi phần tử phù hợp** với bộ lọc **arrayFilters** tương ứng. |

Ba toán tử có phạm vi hoàn toàn khác nhau. **$** không phải ký hiệu thay thế chung cho mọi phần tử, **$[]** không tự xét điều kiện trên từng phần tử và **$[identifier]** không có ý nghĩa nếu thiếu filter cho identifier.

~~~text
                      MongoDB document
                             |
                         items: [...]
                             |
              +--------------+--------------+
              |              |              |
         items.$         items.$[]      items.$[line]
              |              |              |
        Đầu tiên khớp     Tất cả        Mọi phần tử
        theo query        phần tử       khớp arrayFilters
              |              |              |
           Query         Không cần      Query chọn document
        xác định vị trí  lọc phần tử    + arrayFilters chọn item
~~~

Các toán tử này thường xuất hiện trong **$set**, **$inc**, **$unset**, **$mul** và một số update operators khác. Chúng được dùng trong **updateOne()**, **updateMany()**, **bulkWrite()** và các API cập nhật tương ứng của MongoDB Driver. Việc chấp nhận câu lệnh cụ thể còn phụ thuộc phiên bản server, kiểu field và ngữ nghĩa của update operator được dùng.

## 2. Chuẩn bị dữ liệu thực hành

Trong **mongosh**, chọn database chỉ dành cho thử nghiệm:

~~~javascript
use positional_update_lab
~~~

Thêm ba document mẫu. Mỗi dòng hàng là một object trong mảng **items**:

~~~javascript
db.orders.insertMany([
  {
    _id: "ORD-101",
    customerId: "CUS-01",
    status: "OPEN",
    items: [
      {
        sku: "PEN-BLUE",
        qty: NumberInt(2),
        state: "NEW",
        price: NumberDecimal("12000.00")
      },
      {
        sku: "NOTE-A5",
        qty: NumberInt(1),
        state: "NEW",
        price: NumberDecimal("35000.00")
      },
      {
        sku: "PEN-BLUE",
        qty: NumberInt(5),
        state: "NEW",
        price: NumberDecimal("12000.00")
      }
    ]
  },
  {
    _id: "ORD-102",
    customerId: "CUS-02",
    status: "OPEN",
    items: [
      {
        sku: "PEN-BLUE",
        qty: NumberInt(6),
        state: "NEW",
        price: NumberDecimal("12000.00")
      },
      {
        sku: "ERASER",
        qty: NumberInt(3),
        state: "RESERVED",
        price: NumberDecimal("5000.00")
      }
    ]
  },
  {
    _id: "ORD-103",
    customerId: "CUS-03",
    status: "OPEN",
    items: []
  }
]);
~~~

**Lưu ý về thứ tự chạy:** những lệnh update ở các mục sau thay đổi dữ liệu thật trong collection lab. Ví dụ “kết quả dự kiến” được giải thích **từ trạng thái ban đầu** nếu không có ghi chú khác. Để kiểm tra độc lập, dùng một bản sao dữ liệu hoặc tạo lại collection thử nghiệm có kiểm soát; đừng chạy thao tác xóa dữ liệu trên database đang sử dụng thực tế.

Kiểm tra dữ liệu trước khi cập nhật:

~~~javascript
db.orders.find(
  { _id: "ORD-101" },
  { _id: 1, items: 1 }
);
~~~

### 2.1. Phân biệt điều kiện chọn document và điều kiện chọn phần tử

Một câu update có các phần chính:

~~~javascript
db.orders.updateOne(
  { /* filter chọn document */ },
  { /* update expression: đường dẫn và giá trị */ },
  { /* options như arrayFilters, upsert */ }
);
~~~

Với **$**, điều kiện chọn document thường đồng thời giúp xác định vị trí phần tử đầu tiên trong mảng. Với **$[]**, không cần điều kiện riêng trên từng phần tử. Với **$[identifier]**, điều kiện phần tử nằm trong **arrayFilters**, còn filter chính tiếp tục quyết định document nào được cập nhật.

## 3. Toán tử positional $: sửa phần tử đầu tiên khớp

### 3.1. Cú pháp

~~~javascript
db.collection.updateOne(
  { "arrayField.someKey": matchingValue },
  {
    $set: {
      "arrayField.$.otherKey": newValue
    }
  }
);
~~~

Ký hiệu **$** trong **arrayField.$.otherKey** đại diện cho **vị trí của phần tử mảng đầu tiên** được xác định từ điều kiện truy vấn. Ký hiệu này khác dấu **$** đứng trước tên update operator như **$set**.

### 3.2. Ví dụ cập nhật dòng hàng đầu tiên có SKU cho trước

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.sku": "PEN-BLUE"
  },
  {
    $set: {
      "items.$.state": "PACKED"
    }
  }
);
~~~

Document **ORD-101** có **hai** dòng hàng SKU **PEN-BLUE**. Với positional **$**, chỉ **phần tử phù hợp đầu tiên** được cập nhật:

~~~javascript
{
  _id: "ORD-101",
  items: [
    { sku: "PEN-BLUE", qty: 2, state: "PACKED" },
    { sku: "NOTE-A5", qty: 1, state: "NEW" },
    { sku: "PEN-BLUE", qty: 5, state: "NEW" }
  ]
}
~~~

Các field khác như **price** không được in lại trong kết quả rút gọn trên nhưng vẫn còn trong document. Điểm quan trọng là **dòng PEN-BLUE thứ ba chưa được đổi state**, dù cũng khớp SKU.

**Quy tắc:** khi cần cập nhật **tất cả dòng hàng cùng SKU**, không dùng **$** mà cân nhắc **$[line]** với filter **line.sku** tương ứng.

### 3.3. Vì sao filter phải đề cập đến mảng?

Một câu lệnh thiếu điều kiện xác định phần tử như:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$.state": "PACKED" } }
);
~~~

thường không thể xác định vị trí cho **$** và có thể gây lỗi dạng **“The positional operator did not find the match needed from the query”**. Filter chỉ theo **_id** chọn được document, nhưng không nói **phần tử nào trong items** cần cập nhật.

Thêm điều kiện phù hợp:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.sku": "NOTE-A5"
  },
  {
    $set: {
      "items.$.state": "RESERVED"
    }
  }
);
~~~

### 3.4. Khi nhiều điều kiện phải đúng trên cùng một phần tử

Xét document:

~~~javascript
{
  _id: "ORD-X",
  items: [
    { sku: "PEN-BLUE", qty: 1 },
    { sku: "NOTE-A5", qty: 9 }
  ]
}
~~~

Filter:

~~~javascript
{
  "items.sku": "PEN-BLUE",
  "items.qty": { $gte: 5 }
}
~~~

có thể khớp document vì điều kiện SKU đúng ở **phần tử thứ nhất**, còn điều kiện qty đúng ở **phần tử thứ hai**. Hai điều kiện dạng **dotted path** không tự bảo đảm cùng một array element.

Nếu muốn cập nhật **phần tử đầu tiên vừa có sku = PEN-BLUE vừa có qty >= 5**, dùng **$elemMatch**:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    items: {
      $elemMatch: {
        sku: "PEN-BLUE",
        qty: { $gte: 5 }
      }
    }
  },
  {
    $set: {
      "items.$.state": "REQUIRES_CHECK"
    }
  }
);
~~~

Ở dữ liệu ban đầu của ORD-101, chỉ dòng PEN-BLUE có **qty = 5** thỏa toàn bộ điều kiện, nên **$** trỏ đến phần tử thứ ba. Truy vấn **$elemMatch** giúp chỉ định chính xác phần tử thích hợp thay vì vô tình khớp điều kiện ở các dòng hàng khác nhau.

### 3.5. Positional $ trên mảng scalar

Không bắt buộc mảng phải chứa object. Ví dụ:

~~~javascript
db.students.insertOne({
  _id: "STU-01",
  scores: [62, 78, 91, 78]
});

db.students.updateOne(
  {
    _id: "STU-01",
    scores: 78
  },
  {
    $set: {
      "scores.$": 80
    }
  }
);
~~~

Kết quả **scores** là **[62, 80, 91, 78]**. Chỉ giá trị **78 đầu tiên** được thay đổi. Nếu muốn thay **mọi** giá trị 78, cần **$[score]** với **arrayFilters**.

### 3.6. Hạn chế của positional $ cần nhớ

- **Chỉ một phần tử đầu tiên** theo điều kiện match được thay thế bởi **$**.
- **Array field phải xuất hiện trong query** để toán tử xác định vị trí thích hợp.
- Query liên quan **nhiều array fields** có thể làm kết quả positional **mơ hồ**; nên tránh trộn nhiều điều kiện mảng khi cần xác định một phần tử. Dùng điều kiện chính xác và cân nhắc **$[identifier]**.
- **$ không được dùng để traverse nhiều tầng mảng lồng nhau** như hai vị trí mảng độc lập trong một đường dẫn; cần **$[]/$[identifier]** cho nested arrays.
- Với điều kiện phủ định như **$ne**, **$nin** hoặc **$not** trên array, có hạn chế riêng về cách xác định vị trí; một số trường hợp phải đặt điều kiện phủ định **bên trong $elemMatch** nếu muốn dùng positional **$**.
- **Không dùng $ trong upsert** khi thao tác có khả năng insert document mới: không có phần tử đã match để định vị, và ký hiệu **$** có thể bị xem như tên field trong nhánh insert.

### 3.7. $unset với positional $ không xóa phần tử

~~~javascript
db.students.updateOne(
  {
    _id: "STU-01",
    scores: 91
  },
  {
    $unset: {
      "scores.$": ""
    }
  }
);
~~~

Với **$unset** nhắm vào **phần tử của array**, MongoDB đặt vị trí đó thành **null** thay vì co mảng lại. Nếu muốn **loại bỏ các phần tử** khớp điều kiện, hãy dùng **$pull** với quy tắc phù hợp:

~~~javascript
db.students.updateOne(
  { _id: "STU-01" },
  { $pull: { scores: 91 } }
);
~~~

**$pull** loại phần tử khớp ra khỏi mảng; không phải một biến thể của **$set**.

## 4. Toán tử $[]: sửa tất cả phần tử của mảng

### 4.1. Cú pháp

~~~javascript
db.collection.updateOne(
  { /* chọn document */ },
  {
    $set: {
      "arrayField.$[].someKey": value
    }
  }
);
~~~

**$[]** nghĩa là “toàn bộ vị trí trong mảng được chỉ ra bởi đường dẫn”. Nó **không** có identifier và không cần **arrayFilters**.

### 4.2. Gắn trường audit cho tất cả dòng hàng của một đơn

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[].reviewed": false
    }
  }
);
~~~

Với dữ liệu ban đầu, cả ba object trong **items** sẽ có **reviewed: false**. MongoDB cập nhật các phần tử **trong document được chọn**, không phải mọi document trong collection.

Trước khi chạy, cần phân biệt:

- **updateOne()** chọn tối đa một document để cập nhật.
- **$[]** cập nhật toàn bộ phần tử của field mảng trong document đó.

Khi dùng **updateMany()**:

~~~javascript
db.orders.updateMany(
  { status: "OPEN" },
  {
    $set: {
      "items.$[].reviewed": false
    }
  }
);
~~~

MongoDB duyệt các document khớp **status = OPEN** và cập nhật toàn bộ phần tử **items** của **mỗi** document. Điều này vẫn **không** làm toàn bộ lô nhiều document trở thành một transaction nguyên tử.

### 4.3. Tăng mọi giá trị số trong mảng

~~~javascript
db.students.insertOne({
  _id: "STU-02",
  scores: [60, 70, 80]
});

db.students.updateOne(
  { _id: "STU-02" },
  {
    $inc: {
      "scores.$[]": 5
    }
  }
);
~~~

Kết quả là **scores: [65, 75, 85]**. Nếu mảng chứa phần tử không phải số, thao tác **$inc** có thể thất bại; hãy thiết kế schema phù hợp và kiểm tra dữ liệu nguồn.

### 4.4. Mảng rỗng và field không tồn tại

Nếu **items: []**, không có phần tử nào để cập nhật. Thao tác có thể chọn được document nhưng không thay đổi phần tử nào.

Nếu **items** không tồn tại hoặc không phải array tại đường dẫn cần cập nhật, MongoDB có thể từ chối thao tác với lỗi kiểu **“The path 'items' must exist in the document in order to apply array updates”** hoặc lỗi đường dẫn tương ứng.

**$[] không phải công cụ tự tạo mảng và các phần tử bị thiếu**. Nếu ứng dụng cần bảo đảm field tồn tại, hãy xây dựng document với giá trị array hợp lệ ngay khi insert, hoặc có quy trình migration riêng cho document cũ.

### 4.5. Khi nào $[] quá rộng?

Giả sử chỉ các dòng hàng **state = NEW** mới cần đóng gói. Lệnh:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

sẽ đổi cả phần tử **ERASER** đang ở **RESERVED**, mặc dù nghiệp vụ không muốn. **$[] không quan tâm state của từng item**. Khi chỉ một tập con của mảng được phép cập nhật, phải dùng **$[identifier]** với **arrayFilters**.

## 5. Toán tử $[identifier] và arrayFilters: cập nhật phần tử thỏa điều kiện

### 5.1. Cú pháp tổng quát

~~~javascript
db.collection.updateOne(
  { /* filter chọn document */ },
  {
    $set: {
      "arrayField.$[elem].someKey": value
    }
  },
  {
    arrayFilters: [
      { "elem.someKey": condition }
    ]
  }
);
~~~

Trong đó:

- **$[elem]** là placeholder trong đường dẫn update, dùng để chỉ các phần tử của array.
- **elem** là **identifier** do người viết đặt, không phải field thực trong document.
- **arrayFilters** là mảng các document filter xác định **phần tử array nào** tương ứng với identifier đó.
- **Filter chính** vẫn chọn document; **arrayFilters** chọn phần tử bên trong document đã được chọn.

Identifier phải **bắt đầu bằng chữ cái thường** và tiếp theo chỉ gồm ký tự **chữ hoặc số**; ví dụ **line**, **item2**, **grade**. Không dùng khoảng trắng, dấu chấm hoặc gạch dưới trong identifier.

### 5.2. Cập nhật mọi item có số lượng từ 3 trở lên

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "NEEDS_REVIEW"
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 3 } }
    ]
  }
);
~~~

Trong dữ liệu ban đầu của ORD-101:

| Vị trí | sku | qty | Có thỏa line.qty >= 3? | Kết quả |
|---|---|---:|---|---|
| 0 | PEN-BLUE | 2 | Không | Giữ nguyên state. |
| 1 | NOTE-A5 | 1 | Không | Giữ nguyên state. |
| 2 | PEN-BLUE | 5 | Có | State thành NEEDS_REVIEW. |

**$[line] không chỉ lấy phần tử đầu tiên:** nếu có ba item cùng thỏa filter, cả ba đều được cập nhật.

### 5.3. Nhiều điều kiện trên cùng phần tử

Tìm các phần tử **qty >= 3** đồng thời **state = NEW**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "RESERVED"
    }
  },
  {
    arrayFilters: [
      {
        "line.qty": { $gte: 3 },
        "line.state": "NEW"
      }
    ]
  }
);
~~~

Trong một array filter document, các điều kiện field khác nhau thường kết hợp theo **AND**. Vì vậy phần tử phải thỏa đồng thời **qty >= 3** và **state = NEW** mới được cập nhật.

Lưu ý trạng thái **state** của dữ liệu có thể đã thay đổi nếu trước đó bạn chạy ví dụ **NEEDS_REVIEW**. Để so sánh kết quả từng ví dụ, hãy kiểm thử độc lập với document ban đầu.

### 5.4. Tìm nhiều SKU được chọn bằng $in trong arrayFilters

~~~javascript
db.orders.updateMany(
  { status: "OPEN" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": {
          $in: ["PEN-BLUE", "NOTE-A5"]
        }
      }
    ]
  }
);
~~~

Ở mỗi order OPEN, **mọi item** thuộc một trong hai SKU sẽ có **reviewed: true**. Không cần dùng **$or** ở cấp document nếu điều kiện là lựa chọn từ một danh sách giá trị của **cùng field**.

### 5.5. ArrayFilters có thể dùng trực tiếp trên mảng scalar

~~~javascript
db.students.insertOne({
  _id: "STU-03",
  scores: [62, 78, 91, 78]
});

db.students.updateOne(
  { _id: "STU-03" },
  {
    $set: {
      "scores.$[score]": 80
    }
  },
  {
    arrayFilters: [
      { score: 78 }
    ]
  }
);
~~~

Kết quả: **scores: [62, 80, 91, 80]**. Với mảng scalar, filter tham chiếu trực tiếp **score** thay vì **score.someField**.

Có thể dùng điều kiện khoảng:

~~~javascript
db.students.updateOne(
  { _id: "STU-03" },
  {
    $inc: {
      "scores.$[score]": 2
    }
  },
  {
    arrayFilters: [
      { score: { $gte: 90 } }
    ]
  }
);
~~~

Chỉ những điểm thỏa **>= 90** trước khi update được tăng thêm 2. Không có giá trị nào bị “chuyển sang một ngưỡng khác rồi lặp lại vô hạn” trong cùng một thao tác.

### 5.6. $[] và $[identifier] giống và khác nhau

| Khía cạnh | **$[]** | **$[identifier]** |
|---|---|---|
| Chọn phần tử | Mọi phần tử trong array. | Mọi phần tử thỏa filter. |
| Cần **arrayFilters**? | Không. | Có, với filter cho identifier. |
| Dùng với array scalar? | Có. | Có. |
| Dùng với array of objects? | Có. | Có. |
| Có thể cập nhật nhiều phần tử? | Có. | Có. |
| Nên dùng khi | Toàn bộ phần tử thực sự phải được sửa. | Chỉ một tập con dựa trên điều kiện. |

### 5.7. $[identifier] không làm thay đổi toàn bộ document chỉ vì filter phần tử khớp

Giả sử filter chính là **{status: "OPEN"}** và **arrayFilters** chỉ tìm item có **qty >= 10**. Document OPEN không có item đủ điều kiện vẫn có thể được **matchedCount** ghi nhận là document đã match, nhưng **modifiedCount** có thể bằng 0 vì không có phần tử nào thực sự được đổi.

Điều này rất quan trọng khi theo dõi kết quả update: **matchedCount không phải số phần tử array được sửa**.

## 6. Quy tắc khai báo arrayFilters

### 6.1. Một identifier phải có filter tương ứng

Lệnh dưới đây thiếu filter cho **line**:

~~~javascript
// Sai: có $[line] nhưng không có arrayFilters cho line.
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[line].state": "PACKED" } }
);
~~~

MongoDB không biết **line** đại diện cho những phần tử nào nên không thể thực hiện như mong muốn.

Khai báo đúng:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[line].state": "PACKED" } },
  {
    arrayFilters: [
      { "line.sku": "PEN-BLUE" }
    ]
  }
);
~~~

### 6.2. Mỗi identifier chỉ có một filter document tương ứng

Không chia hai điều kiện của cùng identifier thành hai object riêng:

~~~javascript
// Sai: identifier line bị khai báo hai filter document riêng.
{
  arrayFilters: [
    { "line.qty": { $gte: 3 } },
    { "line.state": "NEW" }
  ]
}
~~~

Gộp điều kiện vào **một** document:

~~~javascript
{
  arrayFilters: [
    {
      "line.qty": { $gte: 3 },
      "line.state": "NEW"
    }
  ]
}
~~~

Với điều kiện phức tạp cần AND/OR trên cùng identifier, có thể diễn đạt bằng các toán tử logic được hỗ trợ trong **một filter document**, thay vì tạo nhiều filter documents cho cùng tên.

### 6.3. Một số operator bị hạn chế bên trong arrayFilters

MongoDB **không cho phép** dùng các toán tử sau trong **arrayFilters**:

- **$expr**;
- **$text**;
- **$where**.

Ví dụ muốn lọc theo biểu thức so sánh giữa hai field trong một item, không thể đơn giản đặt **$expr** vào arrayFilters. Có thể cần xem xét biểu diễn dữ liệu, cập nhật bằng **aggregation pipeline** với **$map/$cond** (có giới hạn riêng), hoặc tính điều kiện ở ứng dụng và chuyển thành các tiêu chí được phép.

### 6.4. Không dùng identifier tùy tiện hoặc trùng tên field thật

Trong đường dẫn:

~~~javascript
"items.$[line].state"
~~~

**line** chỉ là placeholder. MongoDB không tự thêm trường tên line vào từng object. Có thể đổi **line** thành **item**, nhưng tên dùng trong đường dẫn và arrayFilters phải thống nhất:

~~~javascript
"items.$[item].state"
arrayFilters: [
  { "item.sku": "PEN-BLUE" }
]
~~~

Không có quy tắc phải đặt identifier cùng tên với array; tên chỉ cần hợp lệ và dễ hiểu.

## 7. Cập nhật mảng lồng nhau bằng nhiều placeholder

Document thực tế có thể chứa nhiều tầng mảng. Ví dụ một shipment có nhiều package, mỗi package có nhiều check:

~~~javascript
db.shipments.insertOne({
  _id: "SHIP-001",
  status: "OPEN",
  packages: [
    {
      tracking: "PKG-A",
      checks: [
        { type: "WEIGHT", passed: false },
        { type: "LABEL", passed: false }
      ]
    },
    {
      tracking: "PKG-B",
      checks: [
        { type: "WEIGHT", passed: false },
        { type: "LABEL", passed: true }
      ]
    }
  ]
});
~~~

### 7.1. Lọc riêng từng tầng mảng

Yêu cầu: trong package **PKG-A**, chỉ đặt check **WEIGHT** thành passed.

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[pkg].checks.$[check].passed": true
    }
  },
  {
    arrayFilters: [
      { "pkg.tracking": "PKG-A" },
      { "check.type": "WEIGHT" }
    ]
  }
);
~~~

Phân tích:

1. **_id** chọn shipment.
2. **$[pkg]** chọn các package có tracking = PKG-A.
3. **$[check]** chọn các check có type = WEIGHT **bên trong các package đã chọn**.
4. **$set** thay đổi **passed** của những phần tử phù hợp.

Sau update, **PKG-A/WEIGHT** thành **true**. Các check khác vẫn giữ nguyên trạng thái.

### 7.2. Kết hợp $[] và $[identifier]

Yêu cầu: đánh dấu **mọi check WEIGHT của tất cả package** đã được duyệt.

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[].checks.$[check].passed": true
    }
  },
  {
    arrayFilters: [
      { "check.type": "WEIGHT" }
    ]
  }
);
~~~

Ở đây:

- **packages.$[]** chọn mọi package;
- **checks.$[check]** chọn check WEIGHT trong từng package;
- không cần filter cho **$[]**, chỉ cần filter cho **check**.

### 7.3. Dùng hai $[] cho tất cả phần tử ở mọi tầng

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[].checks.$[].reviewed": true
    }
  }
);
~~~

Lệnh thêm **reviewed: true** cho mọi check của mọi package trong shipment, nếu cấu trúc các mảng phù hợp. Phạm vi thay đổi rất rộng nên cần xác nhận nghiệp vụ trước khi chạy.

### 7.4. Vì sao positional $ không giải quyết tốt nested arrays?

Một đường dẫn như:

~~~javascript
// Không nên dùng để tìm hai vị trí array độc lập.
"packages.$.checks.$.passed"
~~~

không phải cách đáng tin cậy để định vị hai tầng array chỉ bằng positional **$** thông thường. **$** bị giới hạn trong các trường hợp traverse nhiều array. Các placeholder **$[]** và **$[identifier]** được thiết kế để diễn đạt cập nhật nested arrays rõ ràng hơn.

### 7.5. Chú ý điều kiện trên từng tầng

Nếu update chỉ có filter **pkg.tracking** nhưng không lọc **check.type**, một **$[]** ở tầng check sẽ sửa tất cả các check trong package được chọn. Ngược lại, lọc check nhưng dùng **packages.$[]** sẽ sửa check phù hợp ở **mọi** package.

Khi lồng nhiều array, hãy đọc từ trái sang phải:

~~~text
packages
    -> chọn package nào?
       -> checks
           -> chọn check nào?
               -> cập nhật field nào?
~~~

## 8. ArrayFilters với điều kiện AND, OR và các loại dữ liệu

### 8.1. Điều kiện AND

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "PRIORITY"
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "PEN-BLUE",
        "line.qty": { $gte: 3 }
      }
    ]
  }
);
~~~

Chỉ những line vừa có SKU PEN-BLUE vừa qty >= 3 được đổi. Với dữ liệu ban đầu, đó là line có qty = 5.

### 8.2. Điều kiện OR

Có thể nhóm các tiêu chí OR trong **một filter document**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      {
        $or: [
          { "line.sku": "NOTE-A5" },
          { "line.qty": { $gte: 5 } }
        ]
      }
    ]
  }
);
~~~

Filter dùng **cùng identifier line** trong cả hai nhánh, do đó phù hợp quy tắc mỗi identifier có một filter document. Nếu điều kiện OR chỉ so sánh danh sách SKU của cùng field, **$in** thường ngắn gọn hơn.

### 8.3. Số nguyên, Decimal128 và kiểu BSON

Khi field **price** lưu Decimal128, nên dùng phép gán/tính toán với kiểu BSON phù hợp:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].price": NumberDecimal("11000.00")
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "PEN-BLUE",
        "line.price": { $gt: NumberDecimal("10000.00") }
      }
    ]
  }
);
~~~

**NumberDecimal** giúp giữ ý nghĩa Decimal128 thay vì vô tình lưu double. Ứng dụng Java/Spring Data phải map tương ứng tới **Decimal128/BigDecimal** theo cấu hình.

### 8.4. Phần tử thiếu field

Nếu trong array có object thiếu **state**, filter:

~~~javascript
{ "line.state": "NEW" }
~~~

không chọn phần tử chỉ vì field thiếu. Nếu muốn thêm field cho các phần tử chưa có state, có thể dùng **$exists: false**:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "NEW"
    }
  },
  {
    arrayFilters: [
      { "line.state": { $exists: false } }
    ]
  }
);
~~~

Lệnh này có ý nghĩa migration/chuẩn hóa field. Cần kiểm soát payload: nếu array có phần tử không phải object, không nên mặc định có thể thêm **state** cho chúng một cách an toàn.

## 9. Kết quả cập nhật: matchedCount và modifiedCount

Khi gọi **updateOne/updateMany**, kết quả thường có thông tin tương ứng **matchedCount**, **modifiedCount** và **upsertedId** khi có upsert.

~~~javascript
const result = db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 100 } }
    ]
  }
);

printjson(result);
~~~

Với dữ liệu ban đầu, filter chính **_id = ORD-101** chọn được document, nhưng **không line nào** có qty >= 100. Do đó có thể thấy:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 0,
  upsertedCount: 0,
  upsertedId: null
}
~~~

Điểm quan trọng:

- **matchedCount** là **số document** khớp filter chính, không phải số array element khớp.
- **modifiedCount** là **số document thực sự thay đổi**, không phải số phần tử đã sửa.
- Một document có **100 phần tử được thay đổi** vẫn chỉ tính là **1 document modified**.
- Nếu update đặt giá trị bằng giá trị đã có, document có thể match nhưng không modified.

Muốn biết chính xác số phần tử mảng bị ảnh hưởng cho báo cáo nghiệp vụ, cần thiết kế cách thu thập riêng (ví dụ đọc trước/cộng số lượng theo điều kiện, ghi event hoặc tính toán ở pipeline với những giả định nhất quán thích hợp). Không suy ra trực tiếp từ modifiedCount.

## 10. updateOne và updateMany thay đổi phạm vi document, không thay đổi ngữ nghĩa placeholder

### 10.1. Một document

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[line].state": "BACKORDER" } },
  { arrayFilters: [ { "line.qty": { $gte: 5 } } ] }
);
~~~

Chỉ một document **ORD-101** được xét; mọi item qty >= 5 trong document đó được đổi state.

### 10.2. Nhiều document

~~~javascript
db.orders.updateMany(
  { status: "OPEN" },
  { $set: { "items.$[line].state": "BACKORDER" } },
  { arrayFilters: [ { "line.qty": { $gte: 5 } } ] }
);
~~~

Mỗi document OPEN được xét và mọi line qty >= 5 của document đó được đổi state. Nếu ORD-101 và ORD-102 đều OPEN, các item thỏa điều kiện của **cả hai đơn** có thể bị cập nhật.

Với hệ thống multi-tenant, filter cần thêm **tenantId** lấy từ ngữ cảnh xác thực:

~~~javascript
db.orders.updateMany(
  {
    tenantId: "TENANT-A",
    status: "OPEN"
  },
  {
    $set: {
      "items.$[line].state": "BACKORDER"
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 5 } }
    ]
  }
);
~~~

Ở đây giả định collection production có **tenantId**, còn dữ liệu lab ban đầu không có field này; nếu chạy nguyên lệnh trên lab, sẽ không có document nào match.

**Atomicity:** mỗi thao tác update trên **một document** là nguyên tử theo semantics MongoDB. **updateMany() không tự bảo đảm toàn bộ các document cùng thay đổi như một transaction**. Nếu nghiệp vụ yêu cầu tính nguyên tử trên nhiều document, cần xét multi-document transaction và chi phí của nó.

## 11. Upsert: điểm đặc biệt của $ và $[]/$[identifier]

**Upsert** nghĩa là MongoDB có thể tạo document mới khi không tìm thấy document phù hợp. Với positional updates, không thể giả định array đã tồn tại.

### 11.1. Không dùng positional $ để upsert array item

~~~javascript
// Không phải cách hợp lệ để tạo array phần tử mới khi không có document.
db.orders.updateOne(
  { _id: "ORD-NEW", "items.sku": "PEN-BLUE" },
  { $set: { "items.$.state": "NEW" } },
  { upsert: true }
);
~~~

Khi không có document match, **$** không có vị trí phần tử để thay. MongoDB có hạn chế với positional **$** trong upsert; không dùng thao tác này như cách “tự tạo item”.

Nếu muốn thêm một order mới, hãy tạo document đầy đủ bằng **insertOne()** hoặc một quy trình upsert có payload array rõ ràng, thay vì dựa vào placeholder.

### 11.2. $[] và $[identifier] trong upsert phải thỏa điều kiện equality đặc biệt

Với **$[]** hoặc **$[identifier]**, khi upsert có thể đi vào nhánh insert, MongoDB yêu cầu filter có **điều kiện equality chính xác trên chính array field** để xác lập array ban đầu.

Ví dụ cho array scalar trong collection thử nghiệm:

~~~javascript
db.example_arrays.updateOne(
  { values: [0, 1] },
  {
    $set: {
      "values.$[]": 10
    }
  },
  { upsert: true }
);
~~~

Nếu chưa có document nào match, điều kiện **values: [0, 1]** là một **exact equality** trên array, cho phép MongoDB xử lý nhánh insert và thay các phần tử theo positional update.

Với **$[element]**:

~~~javascript
db.example_arrays.updateOne(
  { values: [0, 1] },
  {
    $set: {
      "values.$[element]": 2
    }
  },
  {
    arrayFilters: [
      { element: 0 }
    ],
    upsert: true
  }
);
~~~

Điều kiện equality phải phù hợp dữ liệu và nghiệp vụ; ví dụ trên chỉ minh họa cú pháp, không phải cách thiết kế API tạo mới phổ biến. Với filter chỉ theo **_id** và không có field array, thao tác upsert dùng **$[]/$[identifier]** có thể thất bại vì đường dẫn array không tồn tại.

### 11.3. Pattern thường an toàn hơn

Đối với create/update khác nhau về semantics:

1. **Create**: dùng **insertOne** hoặc upsert với **$setOnInsert** để khởi tạo **items: []** hay toàn bộ items theo một cấu trúc rõ ràng.
2. **Update existing**: dùng **$/$[]/$[identifier]** sau khi biết array tồn tại.
3. **Append một item mới**: dùng **$push** hoặc **$addToSet** theo nhu cầu, không dùng positional update để tạo phần tử chưa tồn tại.

Nếu nhiều request cạnh tranh tạo/cập nhật, cần thêm unique key và chiến lược retry để xử lý race condition.

## 12. Các giới hạn và lỗi cú pháp phổ biến

### 12.1. Dùng $ nhưng query không xác định phần tử

~~~javascript
// Không đủ để chọn vị trí items.$
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$.state": "DONE" } }
);
~~~

Giải pháp: thêm điều kiện mảng vào query, hoặc chuyển sang **$[line]** nếu cần filter riêng.

### 12.2. Nhầm $[] với “mọi phần tử khớp filter document”

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.state": "NEW"
  },
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

Filter **"items.state": "NEW"** chỉ giúp chọn **document có ít nhất một item NEW**. Một khi document được chọn, **$[] đổi state của mọi item**, kể cả item đã RESERVED hoặc CANCELLED.

Để chỉ đổi các item NEW:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "PACKED"
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

### 12.3. Có arrayFilters nhưng update path không dùng identifier tương ứng

~~~javascript
// Sai: filter line không được tham chiếu trong update path.
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.$[].state": "PACKED" } },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

**$[]** không có placeholder **line** để liên kết với filter. Hãy dùng **$[line]**, hoặc bỏ arrayFilters khi thực sự muốn cập nhật mọi phần tử.

### 12.4. Identifier không hợp lệ

~~~javascript
// Tránh identifier chứa dấu gạch dưới hoặc bắt đầu bằng chữ hoa.
"items.$[line_item].state"
"items.$[Line].state"
~~~

Dùng tên như **lineItem**, **item2**, **grade**; các tên phải bắt đầu bằng chữ cái thường và chứa các chữ cái/số.

### 12.5. Quên lọc tenant/document

~~~javascript
db.orders.updateMany(
  {},
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

Đây là lệnh tác động rộng lên các document có cấu trúc array phù hợp. Không dùng filter **{}** trong production nếu không có mục đích và kế hoạch triển khai rất rõ.

### 12.6. Cập nhật field array không đúng kiểu

Document cũ có thể lưu:

~~~javascript
{ _id: "LEGACY", items: null }
~~~

Những đường dẫn như **items.$[].state** hoặc **items.$[line].state** kỳ vọng **items là array**. Nếu field null, string hoặc cấu trúc không phù hợp, MongoDB có thể báo lỗi và không áp dụng update. Cần migration hoặc validator ngăn schema drift.

### 12.7. $unset array element rồi tưởng đã xóa

~~~javascript
{
  $unset: {
    "scores.$": ""
  }
}
~~~

Với phần tử array, kết quả là **null** ở vị trí tương ứng. Muốn xóa item theo điều kiện, dùng **$pull** và xem lại yêu cầu giữ thứ tự/ý nghĩa chỉ số.

### 12.8. Đổi nhiều trạng thái nhưng không kiểm tra điều kiện chuyển

Nếu một item đang **CANCELLED**, không nên cho lệnh tổng quát đổi thẳng sang **PACKED**. Cần filter theo trạng thái nguồn hợp lệ:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", status: "OPEN" },
  { $set: { "items.$[line].state": "PACKED" } },
  { arrayFilters: [ { "line.state": "NEW" } ] }
);
~~~

Với workflow phức tạp, cần xử lý luật chuyển trạng thái ở lớp domain và đảm bảo các side effect (inventory, payment, fulfillment) được điều phối thích hợp.

## 13. Positional updates và tính nguyên tử, đồng thời

### 13.1. Atomicity cấp document

MongoDB bảo đảm tính nguyên tử của một thao tác update trên **một document**. Ví dụ:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      "items.$[line].state": "PACKED",
      "lastUpdatedBy": "packing-service"
    },
    $currentDate: {
      updatedAt: true
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

Trong **một document ORD-101**, việc đổi state của các item phù hợp và cập nhật metadata xảy ra trong một update operation. Nếu validation thất bại, MongoDB không chấp nhận một document nằm ở trạng thái cập nhật một phần theo cách bình thường.

### 13.2. Atomicity không tự chống lost update trong mọi workflow

Giả sử hai service cùng xử lý một đơn:

- Service A muốn chuyển item NEW sang PACKED.
- Service B muốn hủy item NEW.

Nếu cả hai đều dùng **$[]** mà không kiểm tra state hiện tại, request sau có thể ghi đè state do request trước đã cập nhật. Nên ràng buộc **precondition** vào filter/arrayFilters, như **line.state: "NEW"**, và xử lý **matched/modified count** cùng logic nghiệp vụ.

### 13.3. Optimistic concurrency theo revision

Có thể lưu **revision** của order và chỉ cập nhật khi revision đúng giá trị client đã đọc:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    revision: NumberInt(7)
  },
  {
    $set: {
      "items.$[line].state": "PACKED"
    },
    $inc: {
      revision: 1
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

Ví dụ giả định document có **revision = 7**. Nếu revision đã đổi vì một update khác, filter chính không match và update không diễn ra.

**Điểm cần cân nhắc:** khi filter chính match nhưng **không có line.NEW**, phần **$inc revision** vẫn có thể thay đổi document. Vì thế nếu logic muốn revision chỉ tăng khi thật sự có phần tử đủ điều kiện, hãy bổ sung **điều kiện tồn tại item phù hợp** trong filter chính, ví dụ **"items.state": "NEW"**, và giữ arrayFilters cùng tiêu chí:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    revision: NumberInt(7),
    "items.state": "NEW"
  },
  {
    $set: {
      "items.$[line].state": "PACKED"
    },
    $inc: {
      revision: 1
    }
  },
  {
    arrayFilters: [
      { "line.state": "NEW" }
    ]
  }
);
~~~

Trong thực tế, filter chính cần diễn đạt chính xác điều kiện khiến batch cập nhật có ý nghĩa. Kiểm tra **matchedCount** và **modifiedCount** không thay thế việc định nghĩa invariants.

### 13.4. Retry và tính lặp lại

Phần lớn cập nhật **$set** về cùng một giá trị có tính idempotent ở cấp giá trị field, nhưng **$inc** không có tính chất đó khi ứng dụng tự lặp lại một thao tác đã thực sự thành công.

Ví dụ:

~~~javascript
db.students.updateOne(
  { _id: "STU-02" },
  { $inc: { "scores.$[]": 1 } }
);
~~~

Nếu ứng dụng gửi lại lệnh này như một request nghiệp vụ mới, mọi điểm có thể tăng thêm một lần. Driver MongoDB hỗ trợ retryable writes trong điều kiện nhất định, nhưng không nên nhầm retry tự động của driver với việc ứng dụng tự phát lại các sự kiện không có idempotency key.

## 14. Java Sync Driver: cập nhật mảng bằng các Filters và Updates

Trong **MongoDB Java Sync Driver**, có thể xây dựng các filter bằng **Filters**, update bằng **Updates** và khai báo **arrayFilters** thông qua **UpdateOptions**. Các đường dẫn **items.$.state**, **items.$[].reviewed** và **items.$[line].state** vẫn được viết như chuỗi field path.

### 14.1. Positional $ trong Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

// MongoDatabase database đã được tạo từ MongoClient.
MongoCollection<Document> orders =
        database.getCollection("orders");

Bson filter = Filters.and(
        Filters.eq("_id", "ORD-101"),
        Filters.eq("items.sku", "PEN-BLUE")
);

Bson update = Updates.set("items.$.state", "PACKED");

UpdateResult result = orders.updateOne(filter, update);
System.out.println("Matched: " + result.getMatchedCount());
System.out.println("Modified: " + result.getModifiedCount());
~~~

**Filters.eq("items.sku", ...)** giúp MongoDB xác định phần tử đầu tiên tương ứng với positional **$**. Nếu cùng SKU xuất hiện nhiều lần, chỉ phần tử đầu tiên được cập nhật.

### 14.2. $[] trong Java

~~~java
Bson filter = Filters.eq("_id", "ORD-101");
Bson update = Updates.set("items.$[].reviewed", false);

UpdateResult result = orders.updateOne(filter, update);
~~~

Không cần **UpdateOptions.arrayFilters(...)** vì không dùng placeholder có tên.

### 14.3. $[line] và UpdateOptions.arrayFilters

~~~java
import com.mongodb.client.model.UpdateOptions;
import java.util.List;

Bson filter = Filters.eq("_id", "ORD-101");
Bson update = Updates.set("items.$[line].state", "RESERVED");

UpdateOptions options = new UpdateOptions().arrayFilters(
        List.of(
                new Document("line.state", "NEW")
                        .append("line.qty",
                                new Document("$gte", 3))
        )
);

UpdateResult result = orders.updateOne(filter, update, options);
~~~

Tất cả **line** vừa **state = NEW** vừa **qty >= 3** trong ORD-101 được đổi state sang RESERVED. **UpdateOptions** là nơi driver gửi arrayFilters; tên **line** trong BSON filter phải khớp tên trong đường dẫn update.

### 14.4. Nhiều identifier trong Java

Giả sử collection **shipments** có cấu trúc nested array như Mục 7:

~~~java
MongoCollection<Document> shipments =
        database.getCollection("shipments");

Bson filter = Filters.eq("_id", "SHIP-001");
Bson update = Updates.set(
        "packages.$[pkg].checks.$[check].passed",
        true
);

UpdateOptions options = new UpdateOptions().arrayFilters(
        List.of(
                new Document("pkg.tracking", "PKG-A"),
                new Document("check.type", "WEIGHT")
        )
);

shipments.updateOne(filter, update, options);
~~~

Đường dẫn update dùng **hai identifier khác nhau** nên danh sách arrayFilters chứa **một filter document cho pkg và một filter document cho check**.

### 14.5. Khi dùng POJO thay vì Document

Với POJO mapping, cần lưu ý:

- Field name trong MongoDB có thể khác tên field Java qua các annotation/convention.
- Loại BSON của **qty**, **price**, **state** phải phù hợp codec và validator.
- Tên trong **arrayFilters** không nên được đoán từ tên biến Java; cần đối chiếu field thật trên document.
- Java driver có hỗ trợ typed filters/updates qua các builder, nhưng chuỗi positional path vẫn cần khớp schema lưu trữ.

Đoạn Java ở trên dùng **Document** để minh họa trực tiếp cách MongoDB hiểu update path; một hệ thống production cần bổ sung exception handling, authorization, logs/metrics và kiểm tra kết quả.

## 15. Spring Data MongoDB: Update.filterArray

Trong **Spring Data MongoDB**, có thể sử dụng **MongoTemplate**, **Query**, **Criteria** và **Update**. Với **$[identifier]**, Spring Data cung cấp **Update.filterArray(...)** để gửi arrayFilters đến MongoDB.

### 15.1. Positional $ với MongoTemplate

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

// MongoTemplate mongoTemplate được inject qua Spring.
Query query = Query.query(
        Criteria.where("_id").is("ORD-101")
                .and("items.sku").is("PEN-BLUE")
);

Update update = new Update()
        .set("items.$.state", "PACKED");

UpdateResult result =
        mongoTemplate.updateFirst(query, update, "orders");
~~~

Đây vẫn là MongoDB positional **$**: **phần tử đầu tiên khớp với query**, không phải tất cả.

### 15.2. $[] với MongoTemplate

~~~java
Query query = Query.query(
        Criteria.where("_id").is("ORD-101")
);

Update update = new Update()
        .set("items.$[].reviewed", false);

mongoTemplate.updateFirst(query, update, "orders");
~~~

### 15.3. $[line] bằng Update.filterArray

~~~java
Query query = Query.query(
        Criteria.where("_id").is("ORD-101")
);

Update update = new Update()
        .set("items.$[line].state", "RESERVED")
        .filterArray(
                Criteria.where("line.state").is("NEW")
                        .and("line.qty").gte(3)
        );

UpdateResult result =
        mongoTemplate.updateFirst(query, update, "orders");
~~~

Phương thức **filterArray** của Spring Data thêm điều kiện cho identifier **line**. Lưu ý quan trọng: các điều kiện filterArray có thể **không đi qua cùng quá trình mapping field names như các criteria của entity**, tùy API/phiên bản Spring Data. Khi dùng custom field names như **@Field("qty_value")**, cần xác nhận tên thực trên BSON và version của thư viện.

### 15.4. Lọc nhiều tầng trong Spring Data

~~~java
Query query = Query.query(
        Criteria.where("_id").is("SHIP-001")
);

Update update = new Update()
        .set("packages.$[pkg].checks.$[check].passed", true)
        .filterArray(
                Criteria.where("pkg.tracking").is("PKG-A")
        )
        .filterArray(
                Criteria.where("check.type").is("WEIGHT")
        );

mongoTemplate.updateFirst(query, update, "shipments");
~~~

Mỗi identifier có filter riêng. Đây là ví dụ minh họa Spring Data thao tác với collection theo tên, không yêu cầu khai báo sẵn entity class trong ví dụ.

### 15.5. Chọn updateFirst hay updateMulti

- **updateFirst** cập nhật một document đầu tiên khớp query.
- **updateMulti** cập nhật nhiều document khớp query.
- **$[]/$[identifier]** vẫn hoạt động **bên trong từng document được chọn**.

Khi cập nhật nhiều đơn, phải giới hạn query chính theo tenant/status/time range phù hợp thay vì truyền một query quá rộng.

## 16. Cập nhật mảng bằng aggregation pipeline: trường hợp khác positional update

MongoDB hỗ trợ dạng **update bằng aggregation pipeline** trong các phiên bản thích hợp. Pipeline rất hữu ích khi cần biến đổi array dựa trên logic tính toán, ví dụ thay đổi một số phần tử bằng **$map** và **$cond**.

Ví dụ đặt trạng thái của item có **qty >= 3** mà giữ nguyên các item khác:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  [
    {
      $set: {
        items: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $cond: [
                { $gte: ["$$line.qty", 3] },
                {
                  $mergeObjects: [
                    "$$line",
                    { state: "NEEDS_REVIEW" }
                  ]
                },
                "$$line"
              ]
            }
          }
        }
      }
    }
  ]
);
~~~

Phân tích:

1. **$map** duyệt mảng **items**.
2. **$gte** kiểm tra qty của từng item.
3. **$mergeObjects** tạo object mới giữ các field khác, thay state khi thỏa điều kiện.
4. **$cond** giữ phần tử nguyên vẹn khi không thỏa.
5. **$set** gán lại mảng đã được biến đổi.

Ở ví dụ này **$$line** là biến aggregation pipeline, **khác** identifier trong **$[line]**. Hai cơ chế không thay thế cú pháp cho nhau.

### 16.1. Khi nào chọn $[identifier]?

Chọn **$[identifier]** khi chỉ cần **lọc phần tử theo điều kiện hỗ trợ được trong arrayFilters** rồi áp dụng update operator như **$set/$inc** lên field cụ thể.

### 16.2. Khi nào chọn $map/$cond?

Chọn **aggregation pipeline update** nếu cần:

- Tính giá trị mới dựa trên các field hiện tại của từng phần tử;
- So sánh/biến đổi cấu trúc phức tạp;
- Tạo mảng mới theo biểu thức;
- Dùng một số toán tử aggregation không áp dụng được trong arrayFilters.

**Lưu ý:** pipeline update không dùng positional **$[]/$[identifier]** theo cách của update document thông thường; muốn sửa mảng thì cần biểu thức aggregation phù hợp. Đồng thời pipeline dạng trên sẽ **tính lại cả mảng**, nên phải đo chi phí với array lớn. Trước khi lựa chọn, ưu tiên mô hình dữ liệu và workload thực tế.

## 17. Chỉ số array, $push, $pull và $addToSet khác gì positional update?

MongoDB có nhiều phương pháp thay đổi mảng. Không nên dùng positional operator cho mọi nhu cầu.

| Nhu cầu | Công cụ thường phù hợp |
|---|---|
| Sửa **phần tử đầu tiên thỏa query** | **$** |
| Sửa **tất cả phần tử** | **$[]** |
| Sửa **tập phần tử theo điều kiện** | **$[identifier] + arrayFilters** |
| Thêm phần tử vào cuối array | **$push** |
| Chỉ thêm giá trị nếu chưa tồn tại theo equality phù hợp | **$addToSet** |
| Xóa mọi phần tử phù hợp điều kiện | **$pull** |
| Xóa một phần tử đầu/cuối array | **$pop** |
| Thay một vị trí xác định đã biết | **arrayField.0**, **arrayField.1**, v.v. |
| Biến đổi toàn array dựa trên biểu thức | **$map/$filter** trong aggregation update pipeline |

### 17.1. Sửa theo chỉ số cố định

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $set: { "items.0.state": "PACKED" } }
);
~~~

Đường dẫn **items.0** nhắm trực tiếp phần tử ở index 0, **không kiểm tra SKU**. Nếu thứ tự item thay đổi, cùng câu lệnh có thể sửa một dòng hàng khác. Chỉ dùng cách này khi vị trí đã được bảo đảm và còn hợp lệ.

### 17.2. Thêm dòng hàng

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $push: {
      items: {
        sku: "ERASER",
        qty: NumberInt(1),
        state: "NEW",
        price: NumberDecimal("5000.00")
      }
    }
  }
);
~~~

**$push** thêm phần tử mới, trong khi **$/$[]/$[identifier]** sửa các phần tử đã tồn tại.

### 17.3. Loại các phần tử bị hủy

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $pull: {
      items: { state: "CANCELLED" }
    }
  }
);
~~~

**$pull** thay đổi số lượng phần tử trong array; khác với **$unset** nhắm vào một vị trí array, vốn có thể để lại **null** ở vị trí đó.

### 17.4. Không để array phát triển không giới hạn

Những mảng như **history**, **events** hoặc **logs** có thể tăng liên tục. MongoDB có giới hạn kích thước mỗi BSON document thông dụng **16 MiB**. Nếu cần lưu lịch sử vô hạn, cân nhắc collection sự kiện riêng thay vì nhúng hết vào một document rồi tiếp tục cập nhật.

## 18. Schema validation để positional update an toàn hơn

Schema linh hoạt của MongoDB không tự ngăn một document lưu:

~~~javascript
{
  _id: "BAD-ORDER",
  items: [
    { sku: "PEN-BLUE", qty: "five", state: "NEW" },
    null,
    123
  ]
}
~~~

Những update nhắm tới **items.$[line].qty** hoặc **items.$[].state** có thể không hoạt động đúng khi phần tử không phải object hay **qty** là string.

MongoDB **$jsonSchema** cho phép định nghĩa field **items** phải là array gồm những object có fields/kiểu phù hợp.

Ví dụ tạo collection mới riêng cho lab validation:

~~~javascript
db.createCollection("validated_orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["items"],
      properties: {
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["sku", "qty", "state"],
            properties: {
              sku: { bsonType: "string" },
              qty: {
                bsonType: "int",
                minimum: 0
              },
              state: {
                enum: [
                  "NEW",
                  "RESERVED",
                  "PACKED",
                  "CANCELLED"
                ]
              }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Với validator này, các document insert/update thông thường vi phạm schema có thể bị từ chối, giúp ứng dụng không tạo thêm các array có kiểu lẫn lộn. Tùy domain, còn cần validate **price**, **tenantId**, giới hạn kích thước items và những điều kiện nghiệp vụ khác.

**Schema validation không thay thế business logic.** Ví dụ chuyển **CANCELLED -> PACKED** có thể không hợp lệ dù cả hai đều nằm trong enum state. Điều kiện chuyển trạng thái cần được kiểm soát ở service/update filter phù hợp.

## 19. Index và hiệu năng khi cập nhật phần tử mảng

Positional update có hai loại điều kiện riêng:

1. **Filter chính** giúp MongoDB tìm document.
2. **arrayFilters** giúp xác định **phần tử trong array** sau khi document được chọn.

Một **multikey index** có thể giúp truy vấn các field mảng để tìm document ứng viên. Nhưng index không biến **$[identifier]** thành thao tác không cần đọc/sửa document.

### 19.1. Index cho filter chính

~~~javascript
db.orders.createIndex(
  { customerId: 1, "items.sku": 1 },
  { name: "ix_customer_item_sku" }
);
~~~

Nếu ứng dụng hay tìm order theo customerId và SKU, index này có thể giúp query chọn document:

~~~javascript
db.orders.find({
  customerId: "CUS-01",
  "items.sku": "PEN-BLUE"
}).explain("executionStats");
~~~

Lợi ích cần đo trên dữ liệu đại diện. Với tập dữ liệu vài document, query planner có thể chọn collection scan vì rẻ hơn dùng index.

### 19.2. ArrayFilters không thay thế điều kiện tìm document

Ví dụ:

~~~javascript
db.orders.updateMany(
  {},
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.sku": "PEN-BLUE" }
    ]
  }
);
~~~

Mặc dù **arrayFilters** rất chọn lọc, filter chính **{}** vẫn cho phép xét tất cả document trong collection. Nếu nghiệp vụ muốn chỉ các order của customer CUS-01 và có SKU đó, hãy đưa điều kiện vào query chính:

~~~javascript
db.orders.updateMany(
  {
    customerId: "CUS-01",
    "items.sku": "PEN-BLUE"
  },
  {
    $set: {
      "items.$[line].reviewed": true
    }
  },
  {
    arrayFilters: [
      { "line.sku": "PEN-BLUE" }
    ]
  }
);
~~~

Filter chính giúp giảm số document cần xét; arrayFilters tiếp tục quyết định phần tử nào được sửa. Không phải mọi điều kiện đều cần lặp lại ở cả hai nơi, nhưng việc đặt điều kiện chọn document hợp lý có ảnh hưởng trực tiếp tới hiệu năng.

### 19.3. Mảng lớn vẫn có chi phí

Một document có **5 phần tử** và document có **50.000 phần tử** rất khác nhau về I/O, cache và thời gian tìm/sửa các phần tử. Khi mảng tăng lớn:

- Có thể cân nhắc **tách các phần tử thành collection riêng** nếu truy cập/ghi độc lập;
- Tránh cập nhật hàng loạt **$[]** với array rất lớn khi không cần;
- Dùng projection/đường đọc phù hợp và đo độ trễ của update;
- Cân nhắc contention khi nhiều service sửa cùng một document nóng.

MongoDB bảo đảm atomicity cấp document, nhưng **một document chứa array quá lớn** vẫn có thể trở thành điểm nghẽn về concurrency và kích thước.

### 19.4. Giám sát hiệu năng

Các chỉ số cần chú ý:

| Chỉ số | Ý nghĩa |
|---|---|
| **matchedCount/modifiedCount** | Phân biệt document match và document thay đổi. |
| **Write latency p95/p99** | Phát hiện update lớn hoặc document nóng gây chậm. |
| **totalDocsExamined** trong explain của filter đọc tương ứng | Gợi ý mức độ chọn lọc và hiệu quả index khi tìm document. |
| **Replication lag / write concern latency** | Ảnh hưởng khi update lớn được replicate. |
| **Disk/cache activity** | Áp lực I/O, update document và index. |
| **Write errors/validation errors** | Dấu hiệu schema drift, lỗi đường dẫn array hoặc trạng thái bất hợp lệ. |

Không có một ngưỡng “số phần tử array tối ưu” cho mọi ứng dụng. Cần thử nghiệm với dữ liệu và workload thực tế.

## 20. Thiết kế API cập nhật array an toàn

Giả sử endpoint:

~~~text
PATCH /orders/{orderId}/items/state
~~~

Payload:

~~~json
{
  "sku": "PEN-BLUE",
  "expectedState": "NEW",
  "newState": "PACKED"
}
~~~

Nếu endpoint muốn cập nhật **mọi item cùng SKU đang NEW**, hãy dựng query phía server:

~~~javascript
const orderId = "ORD-101";
const sku = "PEN-BLUE";
const expectedState = "NEW";
const newState = "PACKED";

db.orders.updateOne(
  {
    _id: orderId,
    status: "OPEN",
    items: {
      $elemMatch: {
        sku,
        state: expectedState
      }
    }
  },
  {
    $set: {
      "items.$[line].state": newState
    },
    $currentDate: {
      updatedAt: true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": sku,
        "line.state": expectedState
      }
    ]
  }
);
~~~

Ý nghĩa:

- Filter chính bảo đảm order ở trạng thái OPEN và có ít nhất một item phù hợp.
- ArrayFilters chỉ đổi những item cùng SKU và trạng thái mong đợi.
- Không làm thay đổi những item đã CANCELLED/RESERVED.
- **$currentDate** chỉ có ý nghĩa nếu thao tác update thực sự đi qua filter; với điều kiện **$elemMatch** tương ứng, sẽ có ít nhất một line đủ điều kiện tại thời điểm match.

Trong ứng dụng production còn cần:

1. Lấy **tenantId/authorization** từ phiên làm việc đáng tin cậy, không chỉ tin orderId người dùng gửi.
2. Xác minh **expectedState -> newState** là transition hợp lệ.
3. Kiểm soát độ dài SKU và giá trị enum.
4. Quy định rõ có được cập nhật **tất cả dòng cùng SKU** hay phải chọn một **lineId** duy nhất.
5. Xem xét optimistic locking với **revision** nếu cần phát hiện thay đổi đồng thời.
6. Xử lý lỗi MongoDB, timeout và retry theo mức bảo đảm nghiệp vụ.

Nếu mỗi line có một **lineId** riêng, filter theo **lineId** thường chính xác hơn SKU vì một SKU có thể xuất hiện nhiều lần trong cùng order.

## 21. Câu hỏi luyện tập

### Bài tập 1 — Đổi một dòng hàng đầu tiên

Từ document ORD-101 ban đầu, cập nhật **phần tử đầu tiên** có **sku = PEN-BLUE** thành **state = PACKED** bằng positional **$**. Giải thích vì sao dòng PEN-BLUE còn lại chưa thay đổi.

Gợi ý:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", "items.sku": "PEN-BLUE" },
  { $set: { "items.$.state": "PACKED" } }
);
~~~

### Bài tập 2 — Đổi mọi dòng hàng

Gắn **reviewed: false** cho toàn bộ các phần tử **items** trong ORD-102, không phân biệt state hiện tại.

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  { $set: { "items.$[].reviewed": false } }
);
~~~

### Bài tập 3 — Chọn subset

Chỉ những item ở ORD-102 có **qty >= 5** được đánh dấu **priority: true**.

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  {
    $set: {
      "items.$[line].priority": true
    }
  },
  {
    arrayFilters: [
      { "line.qty": { $gte: 5 } }
    ]
  }
);
~~~

### Bài tập 4 — Kiểm soát trạng thái

Từ trạng thái ban đầu của ORD-102, chỉ chuyển những item **state = NEW** sang **PACKED**. Không được sửa item đang RESERVED.

~~~javascript
db.orders.updateOne(
  { _id: "ORD-102" },
  { $set: { "items.$[line].state": "PACKED" } },
  { arrayFilters: [ { "line.state": "NEW" } ] }
);
~~~

### Bài tập 5 — Lọc nested arrays

Trên SHIP-001, chỉ đặt **passed: true** cho **check WEIGHT của package PKG-B**. Hãy dùng hai identifier trong một update:

~~~javascript
db.shipments.updateOne(
  { _id: "SHIP-001" },
  {
    $set: {
      "packages.$[pkg].checks.$[check].passed": true
    }
  },
  {
    arrayFilters: [
      { "pkg.tracking": "PKG-B" },
      { "check.type": "WEIGHT" }
    ]
  }
);
~~~

### Bài tập 6 — Phân tích matched và modified

Chạy câu update có filter chính theo **_id = ORD-101** và arrayFilters **line.qty >= 100**, rồi quan sát kết quả. Vì sao **matchedCount = 1** nhưng **modifiedCount = 0**?

### Bài tập 7 — Kiểm tra sai phạm vi

Giải thích vì sao truy vấn:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    "items.state": "NEW"
  },
  {
    $set: {
      "items.$[].state": "PACKED"
    }
  }
);
~~~

có thể cập nhật cả các item không phải NEW. Viết lại bằng **$[line]** để chỉ xử lý NEW.

### Bài tập 8 — Thiết kế migration

Một số order cũ có **items: null** hoặc thiếu items, một số order mới có **items: []**. Hãy mô tả kế hoạch chuẩn hóa dữ liệu trước khi chạy **updateMany** dùng **items.$[]**. Vì sao chỉ sửa filter **{status:"OPEN"}** chưa đủ để bảo đảm an toàn?

### Bài tập 9 — Java Driver

Viết đoạn Java dùng **Updates.inc("items.$[line].qty", 1)** và **UpdateOptions.arrayFilters(...)** để tăng qty của tất cả item sku = PEN-BLUE trong ORD-101. Phân tích ý nghĩa retry khi phép cộng có tính không-idempotent.

### Bài tập 10 — Chọn pattern cập nhật

Với từng yêu cầu sau, hãy chọn giữa **$**, **$[]**, **$[id]**, **$pull**, **$push** và aggregation **$map**:

- Cập nhật phần tử đầu tiên có mã hàng cụ thể.
- Đánh dấu tất cả phần tử đã đọc.
- Sửa mọi phần tử có số lượng lớn hơn ngưỡng.
- Xóa các item bị hủy ra khỏi mảng.
- Thêm một item mới.
- Tính giá mới từng item dựa trên giá cũ và nhiều field của chính item.

## 22. Tổng kết

Ba positional update operators dễ học khi luôn tách hai câu hỏi: **“document nào?”** và **“phần tử nào trong mảng?”**

~~~text
Chọn document:
    filter trong updateOne/updateMany
              |
              v
Chọn phần tử array:

    items.$.field
       -> phần tử đầu tiên được xác định từ query

    items.$[].field
       -> mọi phần tử trong array

    items.$[line].field
       -> mọi phần tử thỏa arrayFilters cho line

    packages.$[pkg].checks.$[check].field
       -> nhiều tầng array, mỗi identifier có filter riêng
              |
              v
Áp dụng $set / $inc / $unset / ...
trong phạm vi document được chọn
~~~

Các nguyên tắc cần ghi nhớ:

1. **$** chỉ cập nhật **phần tử phù hợp đầu tiên**, phải có điều kiện trong query để xác định vị trí và không phù hợp cho nhiều tầng mảng.
2. **$[]** cập nhật **mọi phần tử** của mảng trong document khớp filter chính; filter document không thu hẹp các phần tử bên trong.
3. **$[identifier]** cập nhật **tất cả phần tử thỏa arrayFilters**, mỗi identifier cần một filter document hợp lệ.
4. Với **mảng lồng nhau**, kết hợp **$[]** và nhiều **$[identifier]** để diễn đạt các cấp độc lập.
5. **$unset** trên vị trí array khác với **$pull**; một bên có thể để null, một bên thực sự loại phần tử.
6. **updateMany** cập nhật nhiều document, nhưng atomicity được đảm bảo ở **từng document**, không tự biến toàn bộ collection thành một transaction.
7. Khi xử lý **upsert**, đặc biệt cẩn thận vì positional **$** không dùng được cho nhánh insert và **$[]/$[id]** có yêu cầu equality chính xác trên array.
8. **Schema validation, filter theo trạng thái, authorization, optimistic locking và retry policy** là phần của thiết kế ứng dụng, không thể thay thế chỉ bằng lựa chọn positional operator.
9. Với **Java/Spring Data**, cú pháp update path vẫn sử dụng ký hiệu MongoDB; **UpdateOptions.arrayFilters** hoặc **Update.filterArray** truyền điều kiện cho placeholder.

### Tài liệu MongoDB và Spring Data chính thức

- [Positional $ Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional/) — cập nhật phần tử đầu tiên, giới hạn query/upsert/nested arrays.
- [All Positional $[] Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/) — cập nhật mọi phần tử và lưu ý upsert.
- [Filtered Positional $[identifier] Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/) — arrayFilters, identifier, nested arrays và các hạn chế.
- [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/) — cú pháp updateOne/updateMany và update operators.
- [$elemMatch Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — ràng buộc nhiều điều kiện trên cùng một phần tử.
- [$pull Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/pull/) — loại phần tử mảng theo điều kiện.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — Java filters, updates và UpdateOptions.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — MongoTemplate, Update và filterArray.

Khi triển khai trong dịch vụ thật, hãy bắt đầu bằng câu hỏi **“cần sửa phần tử nào và vì sao?”**, sau đó chọn toán tử phù hợp. Sử dụng positional operators đúng cách giúp tránh đọc–ghi đè toàn bộ array, giảm sai phạm vi cập nhật và giữ logic nghiệp vụ có thể kiểm chứng trong một lệnh MongoDB.
