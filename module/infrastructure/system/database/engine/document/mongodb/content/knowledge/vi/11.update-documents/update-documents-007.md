# Thêm phần tử bằng `$push`, `$addToSet` và các tùy chọn `$each`, `$sort`, `$slice` trong MongoDB

## 1. Bài toán: cập nhật một mảng mà không thay cả document

Trong MongoDB, một trường của document có thể chứa **mảng (array)**. Ví dụ, một bài viết có các nhãn `tags`, một học viên có danh sách điểm `scores`, một đơn hàng có các dòng `items` hoặc một người dùng có các sự kiện gần đây `recentEvents`:

```javascript
{
  _id: "POST-01",
  title: "Học MongoDB",
  tags: ["database", "mongodb"],
  recentEvents: [
    { eventId: "E01", action: "CREATED" }
  ]
}
```

Khi cần thêm nhãn hoặc sự kiện, cách đơn giản nhưng dễ lỗi là **đọc cả document → sửa mảng trong ứng dụng → ghi lại mảng**:

```text
Client A đọc tags = ["database"]
Client B đọc tags = ["database"]
Client A ghi ["database", "mongodb"]
Client B ghi ["database", "java"]
Kết quả cuối có thể mất một trong hai phần tử mới
```

Đó là một dạng **lost update** nếu ứng dụng ghi đè dữ liệu cũ mà không có cơ chế kiểm soát cạnh tranh. MongoDB cung cấp các **toán tử cập nhật mảng (array update operators)** để yêu cầu máy chủ sửa trực tiếp trường mảng:

- `$push`: **thêm** giá trị vào mảng, cho phép thêm trùng.
- `$addToSet`: **thêm nếu chưa có giá trị tương đương** trong mảng; không tự xóa các bản trùng đã tồn tại.
- `$each`: thêm **nhiều phần tử** trong cùng một lệnh, hỗ trợ với cả `$push` và `$addToSet`.
- `$sort` và `$slice`: **tùy chọn của `$push`** để sắp xếp và giới hạn số phần tử được giữ lại sau khi thêm; không phải tùy chọn hợp lệ của `$addToSet`.

Các toán tử trên hoạt động bên trong lệnh cập nhật như `updateOne()`, `updateMany()` hoặc các thao tác ghi tương đương, và **một thao tác cập nhật một document có tính nguyên tử ở mức document**. Vì thế, chúng phù hợp hơn việc tự đọc rồi ghi đè mảng khi có nhiều yêu cầu đồng thời.

### Mô hình tư duy

```text
                 Document có trường mảng
                           |
             +-------------+-------------+
             |                           |
          $push                     $addToSet
             |                           |
       Thêm cả khi trùng        Chỉ thêm giá trị chưa có
             |                           |
     Có thể dùng $each          Có thể dùng $each
             |
        Có thể $sort
             |
        Có thể $slice
             |
          Mảng mới
```

Điều quan trọng là chọn toán tử theo **nghĩa nghiệp vụ của mảng**, không chỉ dựa vào việc “muốn thêm một phần tử”. Nhật ký sự kiện có thể cho phép lặp nội dung; danh sách nhãn có thể không cho phép trùng; bảng xếp hạng có thể cần sắp xếp và giới hạn.

## 2. Chuẩn bị collection để thực hành

Các ví dụ dưới đây dùng **mongosh**. Tạo một collection thử nghiệm riêng và chèn dữ liệu mẫu **một lần**:

```javascript
db.arrayUpdateLesson.insertMany([
  {
    _id: "tags",
    title: "Bài viết MongoDB",
    tags: ["database", "mongodb"]
  },
  {
    _id: "scores",
    student: "An",
    scores: [68, 91, 73]
  },
  {
    _id: "recent-events",
    recentEvents: [
      {
        eventId: "E02",
        occurredAt: ISODate("2026-11-10T10:00:00Z"),
        action: "LOGIN"
      },
      {
        eventId: "E01",
        occurredAt: ISODate("2026-11-09T10:00:00Z"),
        action: "REGISTER"
      }
    ]
  },
  {
    _id: "items",
    items: [{ sku: "P01", quantity: 1 }]
  },
  {
    _id: "missing-array",
    note: "Document chưa có trường tags"
  },
  {
    _id: "invalid-array",
    tags: "mongodb"
  }
]);
```

Những ví dụ chạy tuần tự trên **cùng một document** có thể làm kết quả các ví dụ sau thay đổi. Các đoạn mã sẽ ghi rõ khi nào đang mô tả trạng thái ban đầu. Nếu muốn lặp lại kết quả y hệt, dùng collection mới hoặc khởi tạo lại dữ liệu thử nghiệm. Không áp dụng lệnh sửa/xóa thử nghiệm cho dữ liệu sản xuất.

## 3. `$push`: thêm phần tử, kể cả khi đã có phần tử giống nó

Cú pháp cơ bản:

```javascript
db.collection.updateOne(
  { /* điều kiện tìm document */ },
  { $push: { arrayField: newValue } }
);
```

Ví dụ thêm nhãn `"java"` vào bài viết:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "java" } }
);

db.arrayUpdateLesson.findOne(
  { _id: "tags" },
  { _id: 0, tags: 1 }
);
```

Mảng `tags` chuyển từ:

```javascript
["database", "mongodb"]
```

thành:

```javascript
["database", "mongodb", "java"]
```

Nếu chạy lại cùng lệnh, phần tử `"java"` được thêm **lần nữa**:

```javascript
["database", "mongodb", "java", "java"]
```

Đây là **đặc tính của `$push`**, không phải lỗi: nó thêm một phần tử vào mảng và không kiểm tra trùng.

### 3.1. `$push` thích hợp ở đâu?

- Danh sách sự kiện hoặc bước xử lý mà hai sự kiện có cùng nội dung vẫn là hai bản ghi riêng.
- Mảng lưu lịch sử đo đạc, khi các giá trị giống nhau ở hai thời điểm khác nhau vẫn có ý nghĩa.
- Danh sách điểm, sản phẩm hoặc phần tử mà nghiệp vụ cho phép lặp.
- Mảng được duy trì theo thứ tự hoặc giới hạn bằng `$sort`, `$slice`.

Với nhật ký sự kiện quan trọng, mỗi sự kiện thường nên có `eventId` riêng; nếu lượng sự kiện tăng không giới hạn, nên cân nhắc **collection sự kiện riêng** thay vì nhúng hết vào một document.

### 3.2. Một mảng truyền vào `$push` trở thành một phần tử

Xét lệnh:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: ["spring", "java"] } }
);
```

Đây **không phải** yêu cầu thêm hai chuỗi riêng. Cả mảng `["spring", "java"]` được thêm như **một phần tử** của `tags`:

```javascript
[
  "database",
  "mongodb",
  "java",
  ["spring", "java"]
]
```

Ví dụ giả định đã chạy lệnh thêm `"java"` một lần và chưa lặp lại nó. Nếu muốn thêm hai chuỗi riêng biệt, phải dùng `$each`.

**Hệ quả:** không được mặc định `$push` sẽ “trải phẳng” mảng đầu vào. Việc thêm một mảng như một phần tử tạo **mảng lồng nhau**, có thể phá vỡ quy tắc dữ liệu nếu schema mong đợi danh sách toàn chuỗi.

## 4. `$each`: thêm nhiều phần tử cùng lúc

`$each` là **modifier** được đặt bên trong đối số của `$push` hoặc `$addToSet`, không phải một update operator đứng độc lập ở cấp cao:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $push: {
      tags: { $each: ["spring", "java"] }
    }
  }
);
```

Thao tác này thêm **hai phần tử String** vào cuối mảng, giữ nguyên các phần tử đã có, và vẫn cho phép trùng:

```text
Trước: ["database", "mongodb"]
Sau:   ["database", "mongodb", "spring", "java"]
```

Đây là ví dụ trên trạng thái ban đầu của document `"tags"`. Nếu chạy sau các lệnh ở phần 3, những phần tử đã thêm trước đó vẫn tồn tại.

### 4.1. `$each` với phần tử là document

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "items" },
  {
    $push: {
      items: {
        $each: [
          { sku: "P02", quantity: 2 },
          { sku: "P03", quantity: 1 }
        ]
      }
    }
  }
);
```

Mảng `items` sẽ chứa ba document, gồm phần tử `P01` cũ và hai phần tử mới `P02`, `P03`. MongoDB không tự nhận biết `sku` là khóa duy nhất của phần tử; nếu gửi `P02` lần nữa, `$push` vẫn thêm.

### 4.2. Vì sao dùng một lệnh thay vì nhiều lệnh?

Nếu muốn thêm ba phần tử vào cùng mảng:

```javascript
// Ba lần trao đổi lệnh riêng.
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "A" } }
);
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "B" } }
);
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $push: { tags: "C" } }
);
```

Một lệnh `$push` với `$each` giúp diễn đạt ba phần tử cần thêm **trong cùng một cập nhật document**:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $push: {
      tags: { $each: ["A", "B", "C"] }
    }
  }
);
```

Việc gộp thường giảm số lần gọi database và làm yêu cầu nguyên tử ở cấp document rõ ràng hơn. Tuy nhiên, vẫn phải cân nhắc kích thước mảng, số index cần cập nhật và giới hạn kích thước document BSON.

## 5. `$addToSet`: thêm nếu phần tử chưa tồn tại

`$addToSet` phù hợp khi mảng đại diện cho một **tập các giá trị không muốn trùng**, chẳng hạn nhãn đã gắn cho bài viết hoặc những tính năng được bật cho tài khoản.

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "mongodb" } }
);
```

Ở trạng thái ban đầu `tags: ["database", "mongodb"]`, `"mongodb"` đã có, nên lệnh không thêm phần tử mới.

Thêm một giá trị chưa xuất hiện:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "java" } }
);
```

Trong trạng thái ban đầu, MongoDB thêm `"java"` một lần. Nếu chạy cùng lệnh nhiều lần trong khi nội dung mảng không bị những lệnh khác sửa, nó không tiếp tục thêm bản trùng.

### 5.1. `$addToSet` không xóa bản trùng đã có từ trước

Giả sử dữ liệu đã chứa:

```javascript
{ _id: "legacy-tags", tags: ["mongodb", "java", "mongodb"] }
```

Chạy:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "legacy-tags" },
  { $addToSet: { tags: "mongodb" } }
);
```

thì **hai bản `"mongodb"` cũ không tự được gộp lại thành một**. `$addToSet` chỉ ngăn thêm giá trị tương đương mới; nó **không phải toán tử chuẩn hóa hoặc loại trùng toàn bộ mảng**. Muốn dọn dữ liệu cũ, cần chiến lược riêng để phân loại và xây dựng lại mảng theo quy tắc nghiệp vụ.

### 5.2. Thứ tự phần tử không phải hợp đồng của `$addToSet`

`$addToSet` biểu đạt “có/không thuộc tập giá trị” và **không bảo đảm một thứ tự mảng cụ thể** cho ứng dụng. Nếu giao diện cần danh sách tag theo bảng chữ cái, ứng dụng có thể sắp xếp khi đọc hoặc dùng cơ chế dữ liệu khác. Không thay thế yêu cầu sắp xếp ổn định bằng niềm tin rằng các phần tử được thêm sẽ luôn là thứ tự hiển thị phù hợp.

### 5.3. Mảng đầu vào cũng là một giá trị đơn nếu thiếu `$each`

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $addToSet: {
      tags: ["spring", "java"]
    }
  }
);
```

MongoDB xem **toàn bộ mảng `["spring", "java"]` là một giá trị** để so sánh và thêm nếu giá trị mảng đó chưa có. Nó không kiểm tra từng chuỗi `"spring"` và `"java"` riêng biệt.

Để thêm hai chuỗi như hai phần tử của `tags`, dùng `$each` với `$addToSet`.

## 6. `$addToSet` kết hợp `$each`

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $addToSet: {
      tags: {
        $each: ["mongodb", "spring", "java"]
      }
    }
  }
);
```

Với trạng thái ban đầu:

```javascript
["database", "mongodb"]
```

giá trị `"mongodb"` đã tồn tại nên không được thêm lại. Hai giá trị mới `"spring"` và `"java"` được thêm:

```javascript
["database", "mongodb", "spring", "java"]
```

**Khác biệt với `$push + $each`:** `$push` thêm tất cả các phần tử đầu vào (kể cả phần tử trùng); `$addToSet` kiểm tra sự tồn tại của mỗi giá trị trong mảng.

### 6.1. Ví dụ người dùng chọn nhiều sở thích

```javascript
db.users.updateOne(
  { _id: "U01" },
  {
    $addToSet: {
      interests: {
        $each: ["mongodb", "backend", "java"]
      }
    }
  }
);
```

Mỗi giá trị chỉ được thêm nếu chưa có trong `interests`. Tuy nhiên, để định nghĩa thực sự “không trùng”, ứng dụng còn phải quyết định liệu `"MongoDB"` và `"mongodb"` có được xem như một nhãn hay không. Với cách so sánh chuỗi mặc định, khác chữ hoa/chữ thường là khác nhau; nếu yêu cầu không phân biệt kiểu chữ, nên chuẩn hóa mã nhãn ngay tại ranh giới nhập dữ liệu, hoặc dùng quy tắc collation phù hợp và được kiểm chứng.

### 6.2. `$addToSet` so sánh giá trị document theo toàn bộ nội dung

Với phần tử là document, `$addToSet` **không tự xem một trường như khóa**:

```javascript
// Khởi tạo trên collection thử nghiệm riêng.
db.embeddedSetDemo.insertOne({
  _id: "cart",
  items: [{ sku: "P01", quantity: 1 }]
});

// Giá trị document giống hệt: không thêm.
db.embeddedSetDemo.updateOne(
  { _id: "cart" },
  {
    $addToSet: {
      items: { sku: "P01", quantity: 1 }
    }
  }
);

// Cùng sku nhưng khác quantity: đây là giá trị document khác.
db.embeddedSetDemo.updateOne(
  { _id: "cart" },
  {
    $addToSet: {
      items: { sku: "P01", quantity: 2 }
    }
  }
);
```

Kết quả có thể chứa cả:

```javascript
[
  { sku: "P01", quantity: 1 },
  { sku: "P01", quantity: 2 }
]
```

Hai phần tử này **khác nhau về giá trị document**, dù cùng `sku`. Khi đối chiếu document lồng nhau, MongoDB còn xét **thứ tự các trường** trong document: `{ sku: "P01", quantity: 1 }` và `{ quantity: 1, sku: "P01" }` không đương nhiên được `$addToSet` xem là cùng một giá trị.

Nếu nghiệp vụ cần “một SKU xuất hiện tối đa một lần trong giỏ”, `$addToSet` trên **cả document** chưa đủ. Cần thiết kế dữ liệu khác, chẳng hạn một khóa duy nhất làm phần tử của mảng, một map keyed theo SKU, collection dòng hàng với ràng buộc riêng, hoặc câu cập nhật có điều kiện/aggregation pipeline phù hợp.

## 7. `$sort`: sắp xếp mảng sau khi dùng `$push`

`$sort` là **modifier của `$push`**; nó sắp thứ tự các phần tử trong mảng trong quá trình cập nhật. Để dùng `$sort`, cần có `$each`, kể cả khi `$each` chỉ chứa một phần tử.

### 7.1. Sắp xếp mảng số tăng dần

Ví dụ riêng với một document có `scores: [68, 91, 73]`:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "scores" },
  {
    $push: {
      scores: {
        $each: [88, 97],
        $sort: 1
      }
    }
  }
);
```

MongoDB thêm 88 và 97 rồi sắp xếp mảng theo **thứ tự tăng dần**:

```javascript
[68, 73, 88, 91, 97]
```

Trong modifier `$sort` của `$push`:

- `1`: sắp tăng dần.
- `-1`: sắp giảm dần.

### 7.2. Sắp xếp mảng số giảm dần

Trên **một document khác** có trạng thái đầu `[68, 91, 73]`:

```javascript
db.scoreSortDemo.insertOne({
  _id: "descending",
  scores: [68, 91, 73]
});

db.scoreSortDemo.updateOne(
  { _id: "descending" },
  {
    $push: {
      scores: {
        $each: [88, 97],
        $sort: -1
      }
    }
  }
);
```

Kết quả:

```javascript
[97, 91, 88, 73, 68]
```

Không nên đọc kết quả này như “MongoDB chỉ sắp xếp hai phần tử mới”. **Toàn bộ mảng sau khi thêm** được sắp lại.

### 7.3. Sắp xếp mảng chứa document

Giả sử mỗi phần tử có `score` và `candidateId`:

```javascript
db.leaderboardDemo.insertOne({
  _id: "weekly",
  players: [
    { candidateId: "U01", score: 80 },
    { candidateId: "U02", score: 95 }
  ]
});

db.leaderboardDemo.updateOne(
  { _id: "weekly" },
  {
    $push: {
      players: {
        $each: [
          { candidateId: "U03", score: 95 },
          { candidateId: "U04", score: 70 }
        ],
        $sort: { score: -1, candidateId: 1 }
      }
    }
  }
);
```

Mảng được sắp theo `score` giảm dần; nếu hai phần tử có điểm bằng nhau, khóa phụ `candidateId` tăng dần giúp quyết định thứ tự theo quy tắc đã chọn:

```javascript
[
  { candidateId: "U02", score: 95 },
  { candidateId: "U03", score: 95 },
  { candidateId: "U01", score: 80 },
  { candidateId: "U04", score: 70 }
]
```

Nếu không có tiêu chí phụ, không nên giả định các phần tử có cùng khóa sort luôn giữ nguyên thứ tự trước đó. Với dữ liệu quan trọng, dùng khóa phụ ổn định.

### 7.4. Phân biệt `$sort` modifier và `$sort` stage

```javascript
// $sort là modifier CỦA $push, sắp xếp phần tử trong trường mảng.
db.scoreSortDemo.updateOne(
  { _id: "descending" },
  {
    $push: {
      scores: { $each: [99], $sort: -1 }
    }
  }
);

// $sort là aggregation STAGE, sắp thứ tự các document đầu ra.
db.orders.aggregate([
  { $sort: { createdAt: -1 } }
]);
```

Cùng tên `$sort`, nhưng ở câu đầu nó sắp **phần tử bên trong một mảng**, còn ở câu sau sắp **thứ tự document của pipeline**. Việc chọn ngữ cảnh quyết định cú pháp và kết quả.

## 8. `$slice`: giữ lại tối đa N phần tử sau khi `$push`

Một mảng như `recentEvents` có thể chỉ cần lưu **3 sự kiện gần nhất** để hiển thị nhanh. Nếu thêm mãi mà không giới hạn, document ngày càng lớn, tăng chi phí đọc/ghi và có thể chạm giới hạn kích thước BSON document.

`$slice` trong `$push` giúp **cắt mảng sau khi thêm**, cũng yêu cầu có `$each`.

### 8.1. `$slice` dương: giữ N phần tử đầu

```javascript
db.scoreSliceDemo.insertOne({
  _id: "positive",
  scores: [10, 20, 30, 40]
});

db.scoreSliceDemo.updateOne(
  { _id: "positive" },
  {
    $push: {
      scores: {
        $each: [50, 60],
        $slice: 4
      }
    }
  }
);
```

Mảng sau khi thêm là `[10, 20, 30, 40, 50, 60]`. Với `$slice: 4`, MongoDB giữ **4 phần tử đầu**:

```javascript
[10, 20, 30, 40]
```

Ví dụ này cho thấy nếu chỉ nối thêm ở **cuối mảng**, dùng `$slice` dương mà không sắp xếp hoặc thay vị trí thêm, các phần tử mới có thể bị cắt bỏ ngay. Muốn giữ các phần tử mới nhất ở cuối, thường dùng `$slice` âm.

### 8.2. `$slice` âm: giữ N phần tử cuối

```javascript
db.scoreSliceDemo.insertOne({
  _id: "negative",
  scores: [10, 20, 30, 40]
});

db.scoreSliceDemo.updateOne(
  { _id: "negative" },
  {
    $push: {
      scores: {
        $each: [50, 60],
        $slice: -4
      }
    }
  }
);
```

Kết quả:

```javascript
[30, 40, 50, 60]
```

Với `$slice: -4`, MongoDB giữ **4 phần tử cuối** của mảng sau khi thêm. Cách này phù hợp cho một mảng có thứ tự chèn biểu diễn thứ tự thời gian, **nếu yêu cầu được xử lý và thêm đúng thứ tự**. Trong hệ thống có sự kiện đến trễ hoặc không cùng thời gian tạo, nên dùng thêm `$sort` theo thời điểm nghiệp vụ.

### 8.3. `$slice: 0`

```javascript
db.scoreSliceDemo.updateOne(
  { _id: "negative" },
  {
    $push: {
      scores: {
        $each: [70],
        $slice: 0
      }
    }
  }
);
```

`$slice: 0` giữ **không phần tử nào**, khiến mảng thành `[]`. Không dùng nhầm giá trị này khi bạn định giữ “mọi phần tử”. Muốn không giới hạn độ dài, bỏ modifier `$slice`.

### 8.4. `$slice` trong cập nhật và `$slice` trong phép chiếu là hai việc khác

```javascript
// Modifier trong $push: làm THAY ĐỔI mảng được lưu.
db.scoreSliceDemo.updateOne(
  { _id: "positive" },
  {
    $push: {
      scores: { $each: [70], $slice: -3 }
    }
  }
);

// Projection trong find: chỉ chọn phần tử để TRẢ VỀ, không sửa dữ liệu.
db.scoreSliceDemo.find(
  { _id: "positive" },
  { scores: { $slice: -3 } }
);
```

Nếu giao diện chỉ muốn hiển thị ba phần tử mà không muốn xóa phần tử cũ khỏi database, hãy dùng phép chiếu hoặc logic đọc tương ứng. Modifier `$slice` bên trong `$push` **làm mất các phần tử đã bị cắt khỏi mảng được lưu**.

## 9. Kết hợp `$push + $each + $sort + $slice`

Đây là mẫu rất hữu ích khi cần **thêm dữ liệu mới → sắp xếp lại → chỉ giữ phần đầu của mảng theo quy tắc**.

### 9.1. Giữ ba điểm số cao nhất

```javascript
db.topScoreDemo.insertOne({
  _id: "student-01",
  topScores: [68, 91, 73]
});

db.topScoreDemo.updateOne(
  { _id: "student-01" },
  {
    $push: {
      topScores: {
        $each: [88, 97],
        $sort: -1,
        $slice: 3
      }
    }
  }
);

db.topScoreDemo.findOne(
  { _id: "student-01" },
  { _id: 0, topScores: 1 }
);
```

Kết quả:

```javascript
{ topScores: [97, 91, 88] }
```

Quá trình xử lý logic:

1. Mảng ban đầu: `[68, 91, 73]`.
2. Thêm 88 và 97: `[68, 91, 73, 88, 97]`.
3. Sắp xếp giảm dần: `[97, 91, 88, 73, 68]`.
4. Giữ ba phần tử đầu: `[97, 91, 88]`.
5. Lưu mảng kết quả vào document.

Điểm quan trọng: **thứ tự xử lý logic là thêm/định vị → sắp xếp → cắt mảng → lưu**. Viết thứ tự các modifier khác đi trong object cập nhật không làm thay đổi thứ tự xử lý chuẩn này.

### 9.2. Giữ ba sự kiện theo thời điểm mới nhất

Giả sử một document đã có `recentEvents` từ phần chuẩn bị dữ liệu:

```javascript
[
  {
    eventId: "E02",
    occurredAt: ISODate("2026-11-10T10:00:00Z"),
    action: "LOGIN"
  },
  {
    eventId: "E01",
    occurredAt: ISODate("2026-11-09T10:00:00Z"),
    action: "REGISTER"
  }
]
```

Thêm hai sự kiện, một sự kiện mới nhất và một sự kiện đến trễ:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "recent-events" },
  {
    $push: {
      recentEvents: {
        $each: [
          {
            eventId: "E03",
            occurredAt: ISODate("2026-11-11T10:00:00Z"),
            action: "VIEWED_PRODUCT"
          },
          {
            eventId: "E00",
            occurredAt: ISODate("2026-11-08T10:00:00Z"),
            action: "IMPORTED"
          }
        ],
        $sort: { occurredAt: -1, eventId: 1 },
        $slice: 3
      }
    }
  }
);
```

Ba sự kiện còn được lưu, theo thứ tự `E03, E02, E01`. Sự kiện đến trễ `E00` bị loại vì có thời điểm cũ nhất, mặc dù nó được thêm cùng lệnh với `E03`.

Ưu điểm của mẫu này là mảng preview giữ đúng thứ tự theo `occurredAt` và có kích thước tối đa 3. Nhưng nếu cần lưu **lịch sử sự kiện đầy đủ** để kiểm toán hay phân tích, hãy lưu nó trong collection riêng; mảng `recentEvents` chỉ là **bản xem trước có giới hạn**.

### 9.3. Thứ tự giảm dần kết hợp `$slice` âm có nghĩa gì?

Giả sử sau khi thêm các số, ta có dãy giảm dần:

```javascript
[97, 91, 88, 73, 68]
```

`$slice: 3` giữ `[97, 91, 88]`, tức **ba điểm cao nhất**. Ngược lại, `$slice: -3` giữ `[88, 73, 68]`, tức **ba phần tử cuối sau khi sort giảm dần**, không phải ba điểm cao nhất.

Nếu mục tiêu là điểm thấp nhất, có thể chọn sort tăng dần và slice dương. Hãy quyết định hướng sort và dấu của slice cùng nhau.

### 9.4. `$each: []` vẫn hữu ích với `$sort` hoặc `$slice`

Đôi khi không cần thêm phần tử nào, chỉ muốn sắp xếp hoặc cắt bớt mảng đang có:

```javascript
db.topScoreDemo.updateOne(
  { _id: "student-01" },
  {
    $push: {
      topScores: {
        $each: [],
        $sort: -1,
        $slice: 2
      }
    }
  }
);
```

Trên mảng `[97, 91, 88]` từ phần 9.1, kết quả là `[97, 91]`. Đây là một cách biểu đạt cập nhật **sắp xếp/cắt mảng mà không thêm phần tử**. Nó khác với một lệnh `$push` có đối số trống hoàn toàn.

## 10. `$position`: chọn vị trí thêm với `$push`

Dù tên bài tập trung vào `$each`, `$sort`, `$slice`, modifier `$position` giúp hiểu rõ hơn thứ tự các bước trong `$push`.

Theo mặc định, `$push` thêm vào cuối mảng. Nếu muốn thêm ở đầu hoặc vị trí xác định, kết hợp `$position` với `$each`:

```javascript
db.queueDemo.insertOne({
  _id: "queue-01",
  tasks: ["B", "C"]
});

db.queueDemo.updateOne(
  { _id: "queue-01" },
  {
    $push: {
      tasks: {
        $each: ["A"],
        $position: 0
      }
    }
  }
);
```

Kết quả:

```javascript
["A", "B", "C"]
```

`$position: 0` nghĩa là chèn ở đầu mảng. Giá trị chỉ vị trí khác cũng được hỗ trợ theo quy tắc của MongoDB, gồm những vị trí được tính từ cuối mảng; cần hiểu rõ cách đếm khi dùng số âm.

Nếu đồng thời có `$sort`, mảng **sẽ được sắp xếp sau khi chèn**, nên `$position` không nhất thiết quyết định vị trí cuối cùng của phần tử. Ví dụ:

```javascript
db.queueDemo.updateOne(
  { _id: "queue-01" },
  {
    $push: {
      tasks: {
        $each: ["Z"],
        $position: 0,
        $sort: 1
      }
    }
  }
);
```

Sau khi sắp xếp tăng dần, `"Z"` đứng ở cuối, dù được chèn tạm tại vị trí 0.

## 11. Điều kiện dữ liệu và những lỗi khi cập nhật mảng

### 11.1. Trường chưa tồn tại

Nếu document chưa có trường mảng, `$push` hoặc `$addToSet` có thể **tạo trường mới dưới dạng mảng**:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "missing-array" },
  { $push: { tags: "mongodb" } }
);
```

Từ:

```javascript
{ _id: "missing-array", note: "Document chưa có trường tags" }
```

thành document có thêm:

```javascript
{ tags: ["mongodb"] }
```

Nếu dùng `$addToSet` trên một trường thiếu, MongoDB cũng có thể tạo mảng với phần tử mới. Không cần cập nhật trước bằng `$set: { tags: [] }` chỉ vì trường chưa được khởi tạo.

### 11.2. Trường tồn tại nhưng không phải mảng

Nếu document có:

```javascript
{ _id: "invalid-array", tags: "mongodb" }
```

thì:

```javascript
db.arrayUpdateLesson.updateOne(
  { _id: "invalid-array" },
  { $push: { tags: "java" } }
);
```

sẽ bị lỗi vì `tags` đang là **String**, không phải Array. `$addToSet` cũng đòi trường mục tiêu hiện có phải là mảng. Tình huống `tags: null` cũng **không giống trường thiếu** và không thể coi là một mảng rỗng để append.

Ứng dụng nên xác định schema rõ ràng và, khi cần, dùng collection validation để tránh trộn String/Null/Array trong cùng một trường vốn được định nghĩa là danh sách.

### 11.3. `$sort`, `$slice` không dùng trực tiếp với `$addToSet`

Đoạn sau **không phải cú pháp hợp lệ** của `$addToSet`:

```javascript
// KHÔNG DÙNG: $addToSet không hỗ trợ $sort/$slice.
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  {
    $addToSet: {
      tags: {
        $each: ["java"],
        $sort: 1,
        $slice: 3
      }
    }
  }
);
```

Hai nhóm tính năng có phạm vi rõ:

| Modifier | `$push` | `$addToSet` |
|---|:---:|:---:|
| `$each` | Có | Có |
| `$sort` | Có, cùng `$each` | **Không** |
| `$slice` | Có, cùng `$each` | **Không** |
| `$position` | Có, cùng `$each` | **Không** |

Nếu vừa cần **không trùng**, vừa muốn **sắp xếp và giữ tối đa N giá trị**, hãy cân nhắc lại mô hình: có thể dùng aggregation update pipeline để xây dựng mảng mới theo quy tắc, hoặc lưu dữ liệu trong collection riêng có ràng buộc uniqueness phù hợp. Không ghép `$addToSet` với những modifier nó không hỗ trợ.

### 11.4. Kích thước BSON document và mảng không giới hạn

MongoDB giới hạn kích thước **mỗi BSON document** ở mức 16 MiB. Một mảng liên tục `$push` có thể làm document ngày càng lớn, tăng chi phí truyền dữ liệu và cập nhật, thậm chí không thể lưu tiếp nếu vượt giới hạn.

Với các tập có số lượng lớn hoặc tăng vô hạn (log, comments, toàn bộ lượt xem), thường tốt hơn khi dùng **collection con** với khóa tham chiếu về document cha. Mảng nhúng bounded dùng `$slice` phù hợp cho preview hoặc tập dữ liệu nhỏ, không phải nơi lưu mọi sự kiện vĩnh viễn.

### 11.5. Index trên phần tử mảng cũng có chi phí ghi

Nếu tạo index trên `tags`:

```javascript
db.arrayUpdateLesson.createIndex({ tags: 1 });
```

MongoDB có thể tạo **multikey index** cho trường mảng. Index giúp những truy vấn như `{ tags: "mongodb" }`, nhưng mỗi lần sửa mảng có thể phải cập nhật các khóa index liên quan. Không nên chỉ nhìn lợi ích truy vấn đọc mà bỏ qua tác động đến ghi và dung lượng index.

## 12. Tính nguyên tử, cạnh tranh và khả năng gửi lại lệnh

### 12.1. Một document được cập nhật như một đơn vị

Ví dụ hai client cùng thêm phần tử khác nhau vào mảng `tags` của cùng một document:

```javascript
// Client A
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "spring" } }
);

// Client B
db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "docker" } }
);
```

MongoDB thực hiện mỗi cập nhật một document theo ranh giới nguyên tử của thao tác đó. Điều này tránh mẫu lỗi **cả hai đọc cùng mảng cũ rồi từng bên ghi đè toàn bộ**, miễn ứng dụng dùng trực tiếp các toán tử thay vì tự viết lại mảng từ snapshot cũ.

Khi hai client cùng `$addToSet` một giá trị giống nhau, việc kiểm tra thêm phần tử được thực hiện trong thao tác cập nhật; đây là cơ chế phù hợp để ngăn lặp giá trị **theo cách so sánh của `$addToSet`**.

### 12.2. `$push` không tự an toàn với retry ở cấp nghiệp vụ

Giả sử API nhận sự kiện mới và chạy:

```javascript
db.logs.updateOne(
  { _id: "L01" },
  { $push: { events: { eventId: "EVT-100", action: "LOGIN" } } }
);
```

Nếu ứng dụng tự gửi lại cùng lệnh sau timeout, có thể thêm **hai phần tử có cùng `eventId`** vì `$push` không kiểm tra trùng. Khi mục tiêu là lưu mỗi event logic đúng một lần, có thể:

- Tách event thành một document riêng và dùng `eventId` làm khóa duy nhất thích hợp.
- Dùng `$addToSet` nếu toàn bộ giá trị document được tái gửi **giống hệt** và tính duy nhất theo toàn bộ nội dung đáp ứng nghiệp vụ.
- Hoặc thiết kế điều kiện cập nhật/kiểm tra event ID và cơ chế đối soát thích hợp, thay vì coi việc thêm mảng là lệnh idempotent.

Đừng nhầm tự retry một HTTP request bằng lệnh mới với **retryable writes** của MongoDB driver: driver có cơ chế phiên và nhận diện thao tác để hỗ trợ một số tình huống lỗi tạm thời, nhưng nó không biến một chuỗi yêu cầu nghiệp vụ mới thành cùng một thao tác cũ.

### 12.3. `$addToSet` không phải unique constraint cho một trường con

Một mảng `items` chứa:

```javascript
[
  { sku: "P01", quantity: 1 }
]
```

nếu dùng `$addToSet` để thêm `{ sku: "P01", quantity: 2 }` thì MongoDB có thể thêm vì toàn bộ document khác giá trị cũ. Nếu nghiệp vụ cần “một SKU chỉ xuất hiện một lần”, phải diễn đạt quy tắc đó ở cấp mô hình và logic cập nhật. Cũng không nên mặc định **unique multikey index** sẽ ngăn trùng hai phần tử trong cùng document; ràng buộc index có quy tắc riêng và không thể thay cho một ràng buộc uniqueness tùy ý **bên trong mảng**.

### 12.4. Nhiều document khác một document

`updateMany()` có thể áp dụng `$push` hoặc `$addToSet` lên từng document khớp. Nhưng toàn bộ lệnh cập nhật nhiều document **không mặc nhiên nguyên tử như một transaction**. Nếu nghiệp vụ yêu cầu thay đổi nhiều document đồng thời như một đơn vị, cần cân nhắc transaction phù hợp hoặc quy trình phục hồi và đối soát.

## 13. Các mẫu sử dụng trong ứng dụng

### 13.1. Danh sách nhãn không trùng

```javascript
db.posts.updateOne(
  { _id: "POST-01" },
  {
    $addToSet: {
      tags: {
        $each: ["mongodb", "backend", "java"]
      }
    }
  }
);
```

**Chọn `$addToSet`** vì một nhãn có mặt hay không quan trọng hơn số lần người dùng bấm thêm. Nếu cần loại trùng theo mã nhãn nhưng tên hiển thị có thể đổi, lưu mã nhãn ổn định (String) trong `tags`, còn thông tin hiển thị ở collection nhãn.

### 13.2. Giữ năm thông báo gần nhất

```javascript
db.users.updateOne(
  { _id: "U01" },
  {
    $push: {
      notificationPreview: {
        $each: [
          {
            notificationId: "N101",
            createdAt: ISODate("2026-11-11T10:00:00Z"),
            text: "Đã nhận bình luận mới"
          }
        ],
        $sort: { createdAt: -1, notificationId: 1 },
        $slice: 5
      }
    }
  }
);
```

**Chọn `$push + $each + $sort + $slice`** vì preview cần có thứ tự và giới hạn kích thước. Nếu yêu cầu phải ngăn trùng thông báo theo `notificationId`, mẫu này **chưa đủ**: nên lưu bản ghi thông báo đầy đủ theo khóa duy nhất, rồi duy trì preview có đối soát hoặc một thiết kế mảng khác.

### 13.3. Lưu các lần đo có thể trùng giá trị

```javascript
db.sensors.updateOne(
  { _id: "S01" },
  {
    $push: {
      recentReadings: {
        $each: [
          {
            at: ISODate("2026-11-11T10:00:00Z"),
            temperature: 27.5
          },
          {
            at: ISODate("2026-11-11T10:00:05Z"),
            temperature: 27.5
          }
        ],
        $sort: { at: -1 },
        $slice: 10
      }
    }
  }
);
```

Hai phép đo có cùng nhiệt độ vẫn mang **hai thời điểm khác nhau** và đều có giá trị nghiệp vụ; `$addToSet` theo một giá trị số nhiệt độ không phù hợp. Khi lượng dữ liệu đo quá lớn, nên dùng collection/tối ưu lưu chuỗi thời gian phù hợp thay vì mảng lồng vô hạn.

### 13.4. Danh sách người tham gia

```javascript
db.events.updateOne(
  { _id: "EVENT-01" },
  { $addToSet: { participantIds: "USER-08" } }
);
```

Nếu chỉ cần biết người dùng đã tham gia hay chưa, `participantIds` là mảng ID đơn giản, và `$addToSet` giúp tránh thêm ID giống hệt hai lần. Nhưng nếu mỗi người tham gia có trạng thái/đóng tiền riêng hoặc số lượng người tham gia rất lớn, collection quan hệ riêng như `eventParticipants` với unique index trên cặp `eventId, userId` có thể phù hợp hơn.

## 14. Bảng so sánh lựa chọn toán tử

| Nhu cầu | Toán tử/cấu trúc | Có thêm giá trị trùng? | Có tự sắp xếp? | Có giới hạn số phần tử? |
|---|---|---|---|---|
| Thêm đúng một giá trị, chấp nhận trùng | `$push` | Có | Không | Không |
| Thêm nhiều giá trị, chấp nhận trùng | `$push + $each` | Có | Không | Không |
| Thêm một giá trị nếu chưa có | `$addToSet` | Không thêm bản sao tương đương mới | Không | Không |
| Thêm nhiều giá trị chưa có | `$addToSet + $each` | Không thêm bản sao tương đương mới | Không | Không |
| Thêm và sắp xếp mảng | `$push + $each + $sort` | Có | Có | Không |
| Thêm và chỉ giữ N phần tử | `$push + $each + $slice` | Có | Không | Có |
| Thêm, sắp xếp, giữ N phần tử | `$push + $each + $sort + $slice` | Có | Có | Có |
| Vừa không trùng theo khóa con, vừa có thứ tự/giới hạn | Thiết kế khác hoặc update pipeline theo điều kiện nghiệp vụ | Phụ thuộc thiết kế | Có thể | Có thể |

Khi thấy yêu cầu “thêm nhưng không trùng, sắp xếp và giữ 10 phần tử”, đừng ghép tùy tiện `$addToSet` với `$sort` hay `$slice`. Hãy xác định **trùng theo toàn bộ giá trị hay theo khóa con**, và quy tắc nào phải được giữ nguyên tử.

## 15. Cách quan sát kết quả lệnh cập nhật

Ví dụ:

```javascript
const result = db.arrayUpdateLesson.updateOne(
  { _id: "tags" },
  { $addToSet: { tags: "mongodb" } }
);

printjson(result);
```

Thông tin thường gặp trong phản hồi:

- `acknowledged`: thao tác có được xác nhận theo cấu hình ghi hay không.
- `matchedCount`: có bao nhiêu document khớp filter (với `updateOne` tối đa một).
- `modifiedCount`: có bao nhiêu document thực sự bị thay đổi theo kết quả máy chủ công bố.
- `upsertedId`: nếu dùng upsert và thao tác tạo document mới, có thể chứa ID của document đó.

Nếu `$addToSet` thấy giá trị đã có, một thao tác khớp document có thể cho `matchedCount: 1` nhưng `modifiedCount: 0`. Điều đó **không có nghĩa truy vấn không tìm thấy document**; nó chỉ cho biết thao tác không làm thay đổi dữ liệu theo kết quả ghi.

Sau khi cập nhật, có thể đọc lại đúng trường để quan sát:

```javascript
db.arrayUpdateLesson.findOne(
  { _id: "tags" },
  { _id: 0, tags: 1 }
);
```

Với các bài thực hành ghi vào collection chung, hãy tách các ví dụ hoặc đặt lại dữ liệu để tránh kết luận nhầm do những lệnh đã chạy từ trước.

## 16. Bài tập thực hành

### Bài 1 — Phân biệt `$push` và `$addToSet`

Cho:

```javascript
{ _id: "P1", tags: ["mongodb", "java"] }
```

Hãy dự đoán mảng sau khi chạy **từng trường hợp độc lập**:

```javascript
// a
{ $push: { tags: "mongodb" } }

// b
{ $addToSet: { tags: "mongodb" } }

// c
{ $push: { tags: ["spring", "java"] } }

// d
{ $addToSet: { tags: { $each: ["java", "spring"] } } }
```

Giải thích vì sao trường hợp (c) tạo phần tử mảng lồng nhau, còn (d) xử lý từng String riêng.

### Bài 2 — Giữ ba điểm cao nhất

Cho mảng `[62, 88, 71]`. Hãy viết một lệnh `updateOne` để:

1. Thêm điểm 95, 70 và 91.
2. Sắp xếp giảm dần.
3. Giữ đúng ba điểm cao nhất.

Hãy dự đoán kết quả trước khi chạy. Tự giải thích vai trò của `$each`, `$sort: -1` và `$slice: 3`.

### Bài 3 — Giữ những sự kiện gần nhất, kể cả khi đến trễ

Cho:

```javascript
[
  { id: "A", at: ISODate("2026-11-10T10:00:00Z") },
  { id: "B", at: ISODate("2026-11-09T10:00:00Z") }
]
```

Thêm sự kiện `C` ở ngày 11/11 và `D` ở ngày 08/11, chỉ giữ ba sự kiện mới nhất theo `at`. Hãy chọn dấu và giá trị của `$sort`, `$slice` để thứ tự cuối là `C, A, B`. Vì sao chỉ dùng `$slice: -3` mà không sắp xếp theo thời điểm lại không đủ trong trường hợp này?

### Bài 4 — Một SKU có được xuất hiện hai lần?

Cho:

```javascript
{
  _id: "CART-01",
  items: [{ sku: "P01", quantity: 1 }]
}
```

Ứng dụng gọi:

```javascript
db.carts.updateOne(
  { _id: "CART-01" },
  {
    $addToSet: {
      items: { sku: "P01", quantity: 2 }
    }
  }
);
```

Hãy giải thích mảng có thể thay đổi ra sao và vì sao `$addToSet` **không bảo đảm một SKU là duy nhất**. Đề xuất mô hình hoặc ranh giới cập nhật đáp ứng quy tắc “mỗi SKU có một dòng, nếu thêm thì tăng quantity”.

### Bài 5 — Phân biệt cắt dữ liệu được lưu với cắt dữ liệu trả về

Bạn có mảng 10.000 sự kiện trong một document, màn hình chỉ cần ba sự kiện mới nhất. Hãy so sánh:

1. Dùng projection `$slice` khi `find()`.
2. Dùng `$push` với modifier `$sort` và `$slice` khi ghi.
3. Chuyển sự kiện sang collection riêng và chỉ giữ preview trong document cha.

Khi nào mỗi lựa chọn có thể làm **mất lịch sử**? Khi nào dữ liệu tiếp tục tăng đến giới hạn document? Khi nào cần phân trang hoặc index trên collection sự kiện riêng?

### Bài 6 — Phân tích lỗi cập nhật

Cho document:

```javascript
{ _id: "BAD", tags: null }
```

Hãy dự đoán kết quả của:

```javascript
db.example.updateOne(
  { _id: "BAD" },
  { $push: { tags: "mongodb" } }
);
```

Sau đó sửa mô hình dữ liệu để `tags` luôn là mảng khi tồn tại. Giải thích sự khác nhau giữa **trường không tồn tại**, **trường có giá trị null**, và **trường là mảng rỗng** khi áp dụng `$push`.

### Bài 7 — Xây dựng thao tác lặp an toàn

Một dịch vụ nhận sự kiện `eventId = "EVT-100"` từ hàng đợi có thể phát lại. Hãy giải thích:

1. Tại sao `$push` một event object mỗi lần nhận có thể tạo bản trùng?
2. Khi nào `$addToSet` có thể là giải pháp đủ?
3. Nếu một event được gửi lại có cùng `eventId` nhưng khác `receivedAt`, vì sao `$addToSet` trên cả object vẫn có thể thêm?
4. Khi nào nên dùng collection riêng với unique index trên event ID hoặc cặp tenant/event ID?

## 17. Ghi nhớ

**`$push` và `$addToSet` đều sửa trường mảng trong MongoDB, nhưng diễn đạt hai yêu cầu khác nhau.** `$push` luôn thêm phần tử theo ngữ nghĩa của nó; `$addToSet` chỉ thêm nếu giá trị tương đương chưa tồn tại, không tự dọn những phần tử trùng cũ.

**`$each` giúp thêm nhiều phần tử mà không biến cả danh sách đầu vào thành một phần tử mảng lồng nhau.** Nó được dùng với cả `$push` và `$addToSet`.

**`$sort`, `$slice` và `$position` là modifier của `$push`**, dùng cùng `$each` để sắp xếp, cắt ngắn hoặc định vị phần tử trong lúc cập nhật. `$addToSet` không nhận những modifier đó.

**Chọn toán tử theo bất biến nghiệp vụ**: một danh sách nhãn cần tránh trùng, một nhật ký có thể cho phép sự kiện lặp, một mảng preview cần có thứ tự và giới hạn, còn một tập dữ liệu tăng mãi nên có cấu trúc lưu trữ khác. Các thao tác nguyên tử trên một document giúp giảm lỗi cạnh tranh, nhưng không tự bảo đảm chống trùng theo khóa con hoặc đồng bộ trên nhiều document.
