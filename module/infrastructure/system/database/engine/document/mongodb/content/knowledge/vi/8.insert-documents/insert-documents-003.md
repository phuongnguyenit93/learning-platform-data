# Ghi nhiều document theo thứ tự và không theo thứ tự

Khi cần thêm hàng trăm hoặc hàng nghìn document vào MongoDB, việc gửi lần lượt từng lệnh `insertOne()` có thể tạo nhiều lần giao tiếp giữa ứng dụng và database. MongoDB cung cấp `insertMany()` để thêm nhiều document trong một thao tác ở mức API, và `bulkWrite()` để kết hợp nhiều thao tác thêm, cập nhật, thay thế hoặc xóa.

Một lựa chọn quan trọng của hai API này là **`ordered`**:

- **`ordered: true`**: thực hiện các thao tác theo thứ tự được cung cấp và **dừng khi gặp lỗi ghi đầu tiên** trong chuỗi thao tác thông thường.
- **`ordered: false`**: cho phép tiếp tục xử lý các thao tác còn lại dù một hoặc nhiều thao tác gặp lỗi; MongoDB **có thể sắp xếp lại hoặc thực hiện song song** nếu môi trường cho phép, vì thế không được dựa vào thứ tự thực thi như một cam kết.

Quyết định ordered hay unordered ảnh hưởng đến **khả năng tiếp tục sau lỗi, phụ thuộc giữa các document, thông lượng, cách retry và cách đối soát kết quả**. Nó **không** tự biến một batch nhiều document thành transaction nguyên tử.

## 1. Từ `insertOne()` đến `insertMany()`

### 1.1. Thêm từng document

Giả sử hệ thống nhập danh sách sản phẩm vào collection `products`:

```javascript
db.products.insertOne({
  _id: "P1001",
  name: "Bàn phím",
  price: NumberDecimal("350000.00")
});

db.products.insertOne({
  _id: "P1002",
  name: "Chuột",
  price: NumberDecimal("180000.00")
});
```

Mỗi lệnh được gửi và xử lý như một thao tác riêng. Điều này đơn giản khi số bản ghi ít hoặc mỗi bản ghi cần xử lý nghiệp vụ riêng, nhưng với hàng nghìn bản ghi có thể phát sinh thêm round trip và chi phí quản lý kết nối/command.

### 1.2. Thêm nhiều document

```javascript
db.products.insertMany(
  [
    {
      _id: "P1003",
      name: "Màn hình",
      price: NumberDecimal("2900000.00")
    },
    {
      _id: "P1004",
      name: "Tai nghe",
      price: NumberDecimal("650000.00")
    },
    {
      _id: "P1005",
      name: "Webcam",
      price: NumberDecimal("900000.00")
    }
  ],
  { ordered: true }
);
```

Cú pháp tổng quát:

```javascript
db.collection.insertMany(
  [ document1, document2, document3 ],
  {
    ordered: true,
    // writeConcern, bypassDocumentValidation, comment...
  }
);
```

`insertMany()` nhận **một mảng document**. Theo mặc định, `ordered` là `true`. Khi document không có `_id`, driver hoặc MongoDB sẽ bổ sung định danh phù hợp; không nên tự suy đoán `_id` được tạo theo thứ tự tương ứng với timestamp nghiệp vụ.

Thành công trọn vẹn thường cho kết quả chứa thông tin các `insertedIds` hoặc số lượng insert tùy API/driver. Tuy nhiên, hình dạng kết quả và đối tượng lỗi có thể khác giữa `mongosh`, Java driver, Node.js driver và các phiên bản; **ứng dụng cần dùng hợp đồng API của driver đang sử dụng**, không dựa vào chuỗi thông báo lỗi trên terminal.

### 1.3. Một lời gọi API không nhất thiết là một lệnh mạng duy nhất

Driver có thể **chia mảng lớn thành nhiều batch vật lý** theo giới hạn kích thước thông điệp, kích thước BSON và số thao tác của server. MongoDB vẫn áp dụng giới hạn **16 MiB cho mỗi BSON document**. Không nên gửi một document quá 16 MiB rồi kỳ vọng `insertMany()` hoặc bulk batching tự chia document đó.

Đồng thời, `insertMany()` có thể tạo nhiều mục index, cấp phát dữ liệu và ghi journal/replication theo cấu hình. “Một lời gọi” chỉ là giao diện thuận tiện ở client; không đồng nghĩa toàn bộ dữ liệu được ghi bằng một thao tác vật lý duy nhất.

## 2. `ordered: true` — ghi theo thứ tự, dừng khi lỗi

Với chế độ **ordered**, MongoDB xử lý các document theo thứ tự chỉ định. Nếu một thao tác insert gây write error, các document phía sau thao tác lỗi trong luồng ordered thông thường **không được thử tiếp**.

Ví dụ tạo collection thử nghiệm và cố tình chèn trùng `_id`:

```javascript
db.demoOrdered.drop();

db.demoOrdered.insertOne({
  _id: "existing",
  name: "Đã có sẵn"
});

try {
  db.demoOrdered.insertMany(
    [
      { _id: "A", name: "Thêm A" },
      { _id: "existing", name: "Bản ghi trùng ID" },
      { _id: "B", name: "Thêm B" },
      { _id: "C", name: "Thêm C" }
    ],
    { ordered: true }
  );
} catch (error) {
  print("Insert gặp lỗi: " + error.message);
}

db.demoOrdered.find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
```

Kết quả theo logic:

1. `A` được ghi thành công.
2. Document có `_id: "existing"` vi phạm unique index của `_id`; MongoDB báo lỗi **duplicate key**, thường có mã `11000`.
3. `B` và `C` **không được thử** vì thao tác ordered đã gặp lỗi.
4. Document `existing` ban đầu vẫn còn.

Sau lỗi, collection có thể chứa **A** và **existing**. Đây là điểm cần nhớ: **ordered không có nghĩa “rollback toàn bộ mảng nếu một phần tử thất bại”**. Những insert thành công trước lỗi vẫn tồn tại khi không có transaction bảo vệ toàn batch.

Dòng `find().sort()` trong ví dụ chỉ để quan sát kết quả theo `_id`; nó không chứng minh thứ tự ghi vật lý của các record trên ổ đĩa.

### 2.1. Khi nào dùng ordered?

Chọn ordered nếu các thao tác có **phụ thuộc thứ tự** hoặc cần hành vi “gặp lỗi thì dừng để người vận hành sửa”:

- Nhập dữ liệu theo một kịch bản có kiểm tra tuần tự.
- Muốn biết phần đầu batch đã được áp dụng tới thao tác lỗi và không tự động thử phần còn lại.
- Thực hiện những bước bulk mà kết quả của thao tác sau có ý nghĩa phụ thuộc thao tác trước (đặc biệt với `bulkWrite()`).
- Cần quy trình xử lý lỗi dễ quy về một mốc trong danh sách đầu vào.

Tuy nhiên, nếu mỗi document độc lập và mục tiêu là nhập được tối đa số bản ghi hợp lệ, ordered có thể làm cả batch dừng vì một document lỗi.

## 3. `ordered: false` — xử lý những document còn lại dù có lỗi

Đối với **unordered**, MongoDB được phép tiếp tục với các thao tác khác khi một thao tác gặp lỗi. Tài liệu có thể được xử lý theo thứ tự khác thứ tự mảng đầu vào; ở một số triển khai hoặc khi dữ liệu đi qua nhiều shard, hệ thống có thể khai thác tính độc lập để tăng throughput.

Ví dụ dùng collection riêng:

```javascript
db.demoUnordered.drop();

db.demoUnordered.insertOne({
  _id: "existing",
  name: "Đã có sẵn"
});

try {
  db.demoUnordered.insertMany(
    [
      { _id: "A", name: "Thêm A" },
      { _id: "existing", name: "Bản ghi trùng ID" },
      { _id: "B", name: "Thêm B" },
      { _id: "C", name: "Thêm C" }
    ],
    { ordered: false }
  );
} catch (error) {
  print("Một hoặc nhiều thao tác gặp lỗi: " + error.message);
}

db.demoUnordered.find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
```

Tình huống trên:

- `existing` vẫn gây lỗi trùng unique key.
- Các document độc lập `A`, `B` và `C` có thể được ghi thành công dù thao tác ở giữa lỗi.
- Lệnh bulk **vẫn có thể kết thúc bằng lỗi/exception**, bởi có ít nhất một phần tử thất bại; `ordered: false` không có nghĩa “bỏ qua lỗi và luôn trả thành công”.
- Chỉ kết luận **bản ghi nào thực sự đã ghi** bằng kết quả API, thông tin lỗi và/hoặc kiểm tra lại trạng thái dữ liệu; không suy ra đó là một chuỗi ghi có thứ tự vật lý.

Có thể dùng một truy vấn xác nhận:

```javascript
db.demoUnordered.find({
  _id: { $in: ["A", "existing", "B", "C"] }
}).sort({ _id: 1 });
```

Trong ví dụ không có lỗi khác, sẽ thấy `A`, `B`, `C` cùng document `existing` đã tồn tại trước đó. Nhưng nếu gặp thêm lỗi validation, lỗi mạng hoặc write concern, phải xem xét từng trường hợp thay vì khẳng định mọi record hợp lệ chắc chắn đã được ghi.

### 3.1. “Unordered” không có nghĩa “random” hoặc “luôn song song”

`ordered: false` **cho phép** MongoDB/driver tối ưu thứ tự và cách thực hiện; nó không cam kết luôn chạy nhiều thread, không cam kết cải thiện tốc độ theo một hệ số cố định và cũng không có nghĩa các document được lấy ngẫu nhiên.

Một workload nhỏ trên một node, có ít index và không có lỗi có thể có kết quả tương tự ordered. Khi phân phối qua sharded cluster hoặc một batch chứa nhiều record độc lập, unordered có thể hữu ích hơn. Cần đo trên topology, kích thước batch, write concern và tải thực tế.

### 3.2. Không dùng unordered khi các thao tác phụ thuộc lẫn nhau

Giả sử muốn insert document `A` rồi update chính `A` theo thứ tự trong cùng một danh sách `bulkWrite()`. Nếu dùng unordered, việc dựa vào “insert xảy ra trước update” là không an toàn. Hãy dùng ordered, hoặc thiết kế lại để các thao tác độc lập, hoặc dùng một upsert có ý nghĩa rõ ràng.

## 4. So sánh ordered và unordered

| Tiêu chí | `ordered: true` | `ordered: false` |
|---|---|---|
| Giá trị mặc định | **Có** với `insertMany()` và `bulkWrite()` | Phải khai báo |
| Thứ tự thực thi | Theo thứ tự danh sách thao tác | Không nên phụ thuộc thứ tự |
| Khi gặp write error | Dừng chuỗi thao tác còn lại theo ngữ nghĩa ordered | Tiếp tục các thao tác độc lập có thể xử lý |
| Insert đã thành công trước đó | Vẫn được ghi nếu ngoài transaction | Vẫn được ghi nếu ngoài transaction |
| Có trả exception khi một phần lỗi? | Có thể có | Vẫn có thể có |
| Có tự rollback cả batch? | Không | Không |
| Có thể tăng thông lượng trên shard? | Có thể bị giới hạn bởi việc chờ theo thứ tự | Có thể tận dụng thêm tính độc lập, tùy workload |
| Phù hợp | Thứ tự có ý nghĩa hoặc muốn dừng khi lỗi | Nhiều record độc lập, muốn ghi được tối đa phần hợp lệ |
| Điểm phải xử lý | Batch kết thúc sớm và còn dữ liệu chưa thử | Nhiều lỗi, kết quả ghi một phần, không được suy đoán thứ tự |

Phân biệt thêm: **“ordered” là thứ tự thực hiện thao tác ghi**, không phải lời hứa rằng `find()` sau này trả document theo thứ tự chèn. Truy vấn MongoDB muốn có thứ tự xác định phải khai báo `sort()`.

## 5. Lỗi thường gặp trong batch

Một batch có thể thất bại vì nhiều lý do. Những lỗi này có ý nghĩa khác nhau khi thiết kế retry.

### 5.1. Trùng unique index hoặc `_id`

MongoDB mặc định có unique index trên `_id` của collection thông thường. Ngoài ra có thể tạo unique index nghiệp vụ:

```javascript
db.customers.createIndex(
  { emailNormalized: 1 },
  { unique: true }
);
```

Nếu hai document cùng `emailNormalized`, một hoặc cả hai tùy trạng thái ban đầu sẽ không được chèn. Với `ordered: true`, batch dừng tại lỗi đầu tiên. Với `ordered: false`, các document độc lập khác vẫn có thể được xử lý.

**Mã 11000** thường biểu thị duplicate key. Không nên xử lý mọi 11000 như “đã thành công”: nếu payload mới khác bản ghi hiện có, đó có thể là xung đột dữ liệu thật. Retry chỉ được coi là idempotent khi định danh và nội dung nghiệp vụ được kiểm tra theo hợp đồng của ứng dụng.

### 5.2. Lỗi collection validation

Nếu collection có validator, một document sai schema có thể bị từ chối. Ví dụ collection chỉ chấp nhận `price` dạng BSON decimal:

```javascript
db.createCollection("validatedProducts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "price"],
      properties: {
        sku: { bsonType: "string" },
        price: { bsonType: "decimal" }
      }
    }
  }
});

try {
  db.validatedProducts.insertMany(
    [
      { _id: "P1", sku: "P1", price: NumberDecimal("100.00") },
      { _id: "P2", sku: "P2", price: "100.00" },
      { _id: "P3", sku: "P3", price: NumberDecimal("150.00") }
    ],
    { ordered: false }
  );
} catch (error) {
  print(error.message);
}
```

Document `P2` không đúng kiểu decimal nên có thể gây document validation failure; `P1` và `P3` có thể được ghi. Trong môi trường demo, có thể dùng tên collection thử riêng; tránh chạy `drop()` trên collection production.

Các quyền và option như `bypassDocumentValidation` có những điều kiện riêng, không nên dùng để che dữ liệu nhập sai schema.

### 5.3. Document vượt giới hạn BSON

Một document lớn hơn giới hạn BSON không thể được cứu bằng cách đổi `ordered: false`. Cần cắt thành nhiều document theo mô hình hợp lý, hoặc dùng GridFS/object storage với dữ liệu nhị phân lớn. Khi một document trong mảng không hợp lệ, hành vi chính xác còn phụ thuộc vị trí lỗi được phát hiện: driver có thể từ chối trước khi gửi lệnh, hoặc server trả write error. Vì thế **không thể cam kết unordered luôn ghi tất cả phần tử còn lại** với mọi loại lỗi từ client đến server.

### 5.4. Lỗi mạng, timeout và write concern

Có trường hợp client không nhận được phản hồi thành công do mạng gián đoạn nhưng server **đã nhận hoặc đã ghi** dữ liệu. Không nên suy ra “exception nghĩa là chưa có gì được insert”. Tình huống cần phân biệt:

- **Write error:** một thao tác riêng bị từ chối, ví dụ duplicate key hay document validation.
- **Write concern error:** độ xác nhận yêu cầu về replication/journaling không đạt được trong điều kiện tương ứng; một số thay đổi có thể đã được áp dụng, trạng thái durability/replication cần đánh giá.
- **Network/timeout:** ứng dụng không chắc server đã thực thi bao nhiêu thao tác hoặc phản hồi đã đi được tới đâu.

Đối với những lỗi mà trạng thái chưa rõ, phải dựa vào **định danh ổn định, idempotency và truy vấn đối soát**, thay vì retry mù để tránh bản ghi trùng hoặc thiếu.

## 6. `bulkWrite()` — kết hợp nhiều loại thao tác

`insertMany()` chỉ nhận các document để insert. Khi cần insert, update, replace và delete trong một danh sách, dùng `bulkWrite()` của collection:

```javascript
db.inventory.bulkWrite(
  [
    {
      insertOne: {
        document: {
          _id: "SKU-001",
          name: "Sản phẩm mới",
          stock: 20
        }
      }
    },
    {
      updateOne: {
        filter: { _id: "SKU-002" },
        update: { $inc: { stock: 5 } }
      }
    },
    {
      updateOne: {
        filter: { _id: "SKU-003" },
        update: {
          $setOnInsert: {
            name: "Sản phẩm bổ sung",
            stock: 0
          }
        },
        upsert: true
      }
    },
    {
      deleteOne: {
        filter: { _id: "SKU-OLD" }
      }
    }
  ],
  { ordered: true }
);
```

Danh sách này gồm bốn thao tác có ngữ nghĩa riêng. Các phần tử được truyền cho `bulkWrite()` có thể là:

- `insertOne: { document }`;
- `updateOne: { filter, update, upsert? }`;
- `updateMany: { filter, update, upsert? }`;
- `replaceOne: { filter, replacement, upsert? }`;
- `deleteOne: { filter }`;
- `deleteMany: { filter }`.

Tùy API/driver và phiên bản có các option khác. Khi dùng `ordered: true`, thao tác sau có thể dựa vào thay đổi trước nếu chúng cùng nằm trong danh sách tuần tự. Với `ordered: false`, **không được lập kế hoạch nghiệp vụ phụ thuộc thứ tự thao tác**.

### 6.1. Ví dụ thao tác phụ thuộc thứ tự

Giả sử danh sách:

```javascript
db.steps.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "task-1", state: "NEW" }
      }
    },
    {
      updateOne: {
        filter: { _id: "task-1" },
        update: { $set: { state: "READY" } }
      }
    }
  ],
  { ordered: true }
);
```

Ở đây `updateOne` cần bản ghi `task-1` vừa được tạo. Ordered hỗ trợ logic theo trình tự. Nếu `insertOne` lỗi do trùng `_id`, thao tác update phía sau bị dừng; ứng dụng phải quyết định cách xử lý bản ghi cũ.

Nếu dùng unordered, database có thể xử lý update trước insert, khiến update khớp 0 document hoặc tạo ra kết quả khó dự đoán. Dù `ordered: true` đảm bảo thứ tự, **nó không tự bảo đảm atomicity của cả hai thao tác** khi không có transaction.

### 6.2. Chú ý sự khác nhau với bulk write trên nhiều namespace

Một số phiên bản MongoDB/driver hỗ trợ API bulk ở mức client trên nhiều collection/database. Cú pháp, điều kiện hỗ trợ và cấu trúc kết quả có thể khác `db.collection.bulkWrite()` được dùng trong bài. Trước khi triển khai, cần xác nhận đúng API và phiên bản driver; đừng áp dụng cú pháp collection-level cho client-level mà không kiểm tra.

## 7. Kết quả ghi một phần: đọc và đối soát như thế nào?

Với batch được xử lý hoàn toàn, ứng dụng có thể nhận số document insert, số update/delete, `upsertedIds` và các thống kê khác tùy API. Khi gặp lỗi, đối tượng exception có thể cung cấp:

- Loại lỗi và mã lỗi;
- Vị trí thao tác xảy ra lỗi (index trong danh sách);
- Thông tin kết quả phần đã thực hiện;
- Danh sách các write errors;
- Thông tin write concern error nếu có.

Tên trường cụ thể khác giữa `mongosh`, các driver và phiên bản. Vì thế, ví dụ sau minh họa **cách ghi log an toàn về mặt ý tưởng**, không giả định mọi môi trường có cùng cấu trúc error object:

```javascript
try {
  const result = db.ingest.insertMany(documents, {
    ordered: false
  });

  printjson(result);
} catch (error) {
  print("Bulk operation reported an error");
  print(error.message);

  // Nếu driver cung cấp writeErrors/result,
  // ghi các trường có thật theo contract của driver.
  if (error.writeErrors) {
    printjson(error.writeErrors);
  }
}
```

Trong ứng dụng production nên ghi **batch ID**, số input, danh sách các ID đã lên kế hoạch, số thành công/lỗi và nguyên nhân theo mã lỗi. Tránh chỉ ghi `error.message` rồi bỏ kết quả một phần, vì sau đó khó biết document nào cần thử lại.

### 7.1. “Lỗi tại vị trí thứ N” mang nghĩa gì?

Ở chế độ ordered, một lỗi ở vị trí N thường cho biết chuỗi thao tác phía trước đã được thử trước, và các thao tác sau chưa được thử do lệnh dừng. Ở chế độ unordered, vị trí N **xác định phần tử đầu vào gây lỗi**, không chứng minh những phần tử trước N đều đã thành công hoặc được thực thi trước nó.

Nếu driver chia danh sách thành nhiều batch vật lý hoặc xảy ra lỗi chưa rõ trạng thái, ứng dụng nên dựa vào kết quả được công bố và truy vấn đối soát bằng ID thay vì tự diễn giải thứ tự network call.

### 7.2. Kịch bản nhập 1.000 document có 8 lỗi trùng ID

Giả sử 1.000 document độc lập, trong đó 8 document trùng unique key:

- Ordered có thể dừng ngay lỗi đầu tiên, khiến nhiều document hợp lệ chưa được thử.
- Unordered có thể nhập những document hợp lệ khác và báo danh sách 8 lỗi tương ứng.
- Nếu yêu cầu “nhập những gì hợp lệ, báo phần nào trùng” thì unordered thường thuận lợi.
- Nếu yêu cầu “toàn bộ 1.000 phải cùng thành công hoặc cùng thất bại” thì **cả ordered và unordered ngoài transaction đều không đáp ứng**.

Để có tiêu chí hoàn tất rõ ràng, cần chính sách xử lý duplicate: bỏ qua nếu bản ghi cũ tương đương, cập nhật theo quy tắc hợp nhất, hay báo xung đột để can thiệp.

## 8. Atomicity và transaction: ordered/unordered không quyết định tất cả

Một thao tác insert **một document** được MongoDB thực hiện nguyên tử ở cấp document. Tuy nhiên, gọi `insertMany()` với 100 document trong điều kiện thông thường không có nghĩa “100 document là một transaction ACID duy nhất”.

Ví dụ không có transaction:

```text
Batch ordered:
  D1 -> thành công
  D2 -> thành công
  D3 -> lỗi duplicate key
  D4 -> chưa được thử

Sau lệnh:
  D1, D2 vẫn có trong collection.
  D3 không được thêm.
  D4 không được thử.
```

Khi nghiệp vụ thực sự đòi hỏi **tất cả hoặc không gì cả**, có thể dùng multi-document transaction trên topology hỗ trợ, đồng thời xử lý retry và lỗi commit phù hợp với driver.

Ví dụ ý tưởng trong `mongosh`:

```javascript
const session = db.getMongo().startSession();

try {
  const sessionDb = session.getDatabase(db.getName());
  const orders = sessionDb.getCollection("orders");

  session.startTransaction();

  orders.insertMany(
    [
      { _id: "ORD-101", customerId: "C1", total: 100 },
      { _id: "ORD-102", customerId: "C2", total: 200 }
    ],
    { ordered: true }
  );

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (abortError) {
    // Có thể transaction đã tự kết thúc hoặc commit đang chưa rõ kết quả.
    // Xử lý theo loại lỗi thực tế.
  }

  print("Transaction error: " + error.message);
} finally {
  session.endSession();
}
```

Đây là ví dụ luồng cơ bản. Trong ứng dụng thực, transaction callback/helper của driver có thể hỗ trợ cơ chế retry cho các lỗi phù hợp; ứng dụng vẫn phải hiểu trường hợp **kết quả commit chưa rõ**.

Trong transaction, lỗi thao tác có thể khiến transaction bị abort và các write trước đó không được commit. **Đừng xem `ordered: false` như cách bảo đảm tiếp tục ghi từng phần bên trong một transaction đã gặp lỗi**. Nếu cần xử lý từng document hợp lệ, hãy cân nhắc validation trước và chạy các batch độc lập ngoài transaction, hoặc dùng transaction theo một ranh giới nghiệp vụ nhỏ hơn.

### 8.1. Khi nào không nên đưa toàn bộ batch vào transaction?

Transaction tăng chi phí đồng bộ và sử dụng tài nguyên; transaction dài/chứa nhiều thay đổi có thể tạo áp lực lớn, gặp giới hạn thời gian hoặc phát sinh xung đột. Nhập hàng triệu bản ghi độc lập thường phù hợp với **batch có checkpoint và retry idempotent** hơn là một transaction khổng lồ.

Ngược lại, ghi một đơn hàng cùng các biến động tồn kho liên quan có thể cần transaction vì invariant nghiệp vụ quan trọng hơn thông lượng batch.

## 9. Tính idempotent khi nhập nhiều document

Trong thực tế, request bulk có thể bị retry do timeout, mất kết nối hoặc consumer chạy lại dữ liệu. Nếu mỗi lần retry lại tạo `_id` mới, cùng một sự kiện nghiệp vụ có thể biến thành nhiều document trùng nội dung.

### 9.1. Dùng ID ổn định từ nguồn dữ liệu

Ví dụ mỗi sự kiện có `eventId` duy nhất từ hệ thống nguồn:

```javascript
const events = [
  {
    _id: "event-1001",
    source: "partner-A",
    payload: { type: "CREATED", orderId: "ORD-5" }
  },
  {
    _id: "event-1002",
    source: "partner-A",
    payload: { type: "PAID", orderId: "ORD-5" }
  }
];

db.partnerEvents.insertMany(events, { ordered: false });
```

Nếu retry với cùng ID, unique index trên `_id` có thể báo duplicate key thay vì tạo bản sao mới. Nhưng **không được tự coi mọi duplicate key là thành công**: cần so sánh thuộc tính quan trọng hoặc hash nội dung để xác minh duplicate thực sự cùng sự kiện.

### 9.2. Dùng upsert với `$setOnInsert` khi thích hợp

Nếu mục tiêu là “có bản ghi với ID này, nếu chưa có thì tạo”, có thể thay insert bằng upsert:

```javascript
db.partnerEvents.bulkWrite(
  events.map(event => ({
    updateOne: {
      filter: { _id: event._id },
      update: { $setOnInsert: event },
      upsert: true
    }
  })),
  { ordered: false }
);
```

Nếu document với `_id` đã tồn tại, `$setOnInsert` không thay nội dung cũ. Đây là lựa chọn cho ingest kiểu insert-if-absent, nhưng nếu payload mới khác payload cũ, ứng dụng vẫn cần phát hiện và xử lý xung đột theo nghiệp vụ. Những đợt upsert đồng thời cũng cần có unique index phù hợp và chiến lược retry với duplicate-key race.

### 9.3. Batch ID và checkpoint tiến độ

Một ingestion job có thể dùng:

```text
jobId = import-2026-11-14
batchIndex = 0001
sourceRange = lines 000001–001000
documentIds = [event-1001, ..., event-2000]
status = completed / partially_completed / retry_needed
```

Đây là metadata ở tầng ứng dụng, không phải cấu trúc bắt buộc của MongoDB. Nó hỗ trợ khởi chạy lại có kiểm soát, đối soát document theo ID và tránh mất dữ liệu khi job dừng giữa chừng.

## 10. Hiệu năng: dùng unordered khi nào có lợi?

Một batch có thể nhanh hay chậm tùy nhiều yếu tố:

| Yếu tố | Tác động |
|---|---|
| Số document và kích thước BSON | Batch nhỏ quá làm nhiều round trip; quá lớn tăng memory và thời gian xử lý |
| Số index | Mỗi insert phải cập nhật index, bao gồm unique và multikey |
| Write concern | `w: 1`, `majority` và yêu cầu journal có đặc tính xác nhận/durability khác nhau |
| Sharding | Unordered có thể khai thác nhiều shard cho các thao tác độc lập, nhưng còn tùy shard key và phân phối dữ liệu |
| Network latency | Nhiều insert đơn lẻ bị chi phí round trip rõ rệt hơn |
| Document validation | Schema validation có chi phí; dữ liệu sai gây lỗi batch |
| Concurrent writers | Nhiều job cùng ghi gây cạnh tranh CPU/I/O/index/cache |
| Retry/duplicate | Batch nhiều lỗi có thể tốn công phân loại và đối soát |

**Không có quy tắc “unordered luôn nhanh hơn ordered X lần”**. Nếu dữ liệu nhỏ, không phân shard hoặc hệ thống đang bị giới hạn bởi I/O/index, sự khác biệt có thể không đáng kể. Khi ordered có lỗi sớm, nó thực thi ít thao tác hơn nên so thời gian đơn thuần với unordered là so sánh không công bằng: phải đo **số document thành công mỗi giây**, CPU, I/O, p95/p99 latency và số lỗi.

### 10.1. Chọn kích thước batch

Để xử lý hàng triệu record, hãy chia thành các batch có kích thước phù hợp với workload và khả năng RAM/network. Không cần tự nhồi tất cả vào một `insertMany()` khổng lồ vì driver có thể phải chia lệnh, xử lý danh sách kết quả/lỗi và giữ nhiều dữ liệu trong bộ nhớ.

Một quá trình import thường:

1. Đọc/parse dữ liệu đầu vào theo streaming hoặc chunk.
2. Chuẩn hóa schema và tạo ID ổn định.
3. Gửi một batch các document độc lập.
4. Ghi nhận kết quả, lỗi và checkpoint.
5. Retry các phần tử chưa rõ trạng thái theo chính sách idempotent.
6. Tiếp tục batch kế tiếp.

Kích thước batch không chỉ được quyết định bằng **số document** mà còn bởi byte BSON mỗi document, index và mức đồng thời.

### 10.2. Ví dụ nhập theo lô trong `mongosh`

Ví dụ này minh họa cách chia dữ liệu giả lập thành lô; các tên collection được chọn để phục vụ thử nghiệm:

```javascript
const batchSize = 500;
let batch = [];

for (let i = 0; i < 2000; i++) {
  batch.push({
    _id: "sample-" + i,
    category: "demo",
    value: i,
    createdAt: new Date()
  });

  if (batch.length >= batchSize) {
    try {
      db.bulkDemo.insertMany(batch, { ordered: false });
    } catch (error) {
      print("Batch write issue: " + error.message);
      // Trong ứng dụng thật: ghi log các ID của batch rồi đối soát.
    }
    batch = [];
  }
}

if (batch.length > 0) {
  db.bulkDemo.insertMany(batch, { ordered: false });
}
```

Ở ví dụ trên, catch chỉ minh họa, **chưa phải importer production**: một lỗi mạng có thể khiến trạng thái một phần batch chưa rõ; bắt lỗi rồi đi tiếp mà không lưu checkpoint/đối soát có thể gây thiếu dữ liệu. Khi chuyển thành ứng dụng thật cần mở rộng nhánh lỗi thay vì chỉ in message.

## 11. Ảnh hưởng của thứ tự đến dữ liệu và truy vấn

### 11.1. Thứ tự insert không phải thứ tự `find()`

```javascript
db.logs.insertMany(
  [
    { _id: "L1", sequence: 1 },
    { _id: "L2", sequence: 2 },
    { _id: "L3", sequence: 3 }
  ],
  { ordered: true }
);

// Không giả định kết quả luôn theo sequence:
db.logs.find();

// Nếu muốn thứ tự nghiệp vụ:
db.logs.find().sort({ sequence: 1, _id: 1 });
```

MongoDB không cam kết thứ tự hiển thị mặc định của `find()` là thứ tự insert trong mọi lần chạy. Index, query plan, update/migration và sharding đều có thể ảnh hưởng thứ tự quét tự nhiên. Thứ tự hiển thị phải được xác định bằng `sort()`.

### 11.2. `ordered: false` và phụ thuộc giữa các document

Nếu nghiệp vụ yêu cầu “tạo parent xong mới tạo child”, việc gửi chúng thành unordered batch không tự áp dụng foreign key hay transaction. MongoDB không có foreign key tương tự RDBMS cho các collection thông thường; nếu cần bảo toàn liên kết nghiệp vụ, ứng dụng phải thiết kế các bước và validation phù hợp.

Đối với mảng `insertMany()` chỉ insert document, thao tác độc lập là điều kiện thuận lợi để dùng unordered. Với `bulkWrite()` nhiều loại thao tác, phụ thuộc giữa phần tử là nguy cơ rõ hơn.

### 11.3. “Thành công theo thứ tự” vẫn không bảo đảm visibility xuyên nhiều query

Ngoài transaction, một client khác có thể quan sát collection giữa lúc batch còn đang chạy; MongoDB không làm toàn bộ batch hiện ra như một đối tượng bất khả phân. Với dữ liệu đang được ingest, cần cơ chế phát hành trạng thái như `importStatus: "READY"` sau khi hoàn tất và đối soát, hoặc transaction theo nhu cầu, nếu reader chỉ được nhìn thấy bộ dữ liệu hoàn chỉnh.

## 12. Chiến lược chọn chế độ theo tình huống

| Tình huống | Chế độ nên cân nhắc | Lý do |
|---|---|---|
| Nhập danh mục từ CSV, mỗi sản phẩm độc lập | `ordered: false` | Một dòng lỗi không làm dừng các dòng hợp lệ khác |
| Seed dữ liệu demo cần dừng tại sai sót đầu tiên | `ordered: true` | Dễ phát hiện lỗi và không thử các thao tác sau |
| Bulk gồm insert rồi update cùng ID | `ordered: true` | Giữ phụ thuộc tuần tự |
| Nhập dữ liệu qua nhiều shard, thao tác độc lập | `ordered: false` | Có thể khai thác phân bố ghi khi điều kiện phù hợp |
| Yêu cầu tất cả document cùng commit hoặc rollback | Transaction phù hợp | Ordered/unordered đơn lẻ không đáp ứng atomicity toàn batch |
| Consumer nhận event có thể retry | Unordered hoặc upsert idempotent | Ưu tiên ID ổn định, đối soát và xử lý duplicate |
| Ghi tồn kho và đơn hàng có bất biến liên quan | Transaction hoặc thiết kế nguyên tử phù hợp | Không đánh đổi tính đúng đắn lấy throughput |
| Di chuyển dữ liệu nhiều triệu record | Batch nhỏ, checkpoint, retry | Cần kiểm soát memory, lỗi một phần, khả năng tiếp tục |

## 13. Quy trình xử lý lỗi cho import thực tế

Đối với mỗi batch, không nên chỉ ghi “success/failed” ở mức toàn bộ. Một quy trình đáng tin cậy có thể gồm:

**Bước 1 — Chuẩn hóa input trước khi ghi.** Kiểm tra kiểu dữ liệu, các trường bắt buộc, giới hạn kích thước, giá trị unique và gán ID ổn định. Validation ở ứng dụng giúp lỗi dễ đọc nhưng không thay thế unique index/validator ở database.

**Bước 2 — Chọn chế độ theo tính độc lập.** Nếu các document độc lập, `ordered: false` giúp tiếp tục sau lỗi từng document. Nếu có phụ thuộc giữa các thao tác, dùng ordered hoặc chuyển sang các bước/transaction có ranh giới rõ ràng.

**Bước 3 — Ghi kết quả có cấu trúc.** Lưu số input, những ID đã thử, số thành công, lỗi theo mã và vị trí (nếu driver cung cấp), cũng như write concern/network errors.

**Bước 4 — Phân loại trạng thái chưa rõ.** Với lỗi mạng/timeout, tra cứu các ID trong database hoặc dùng cơ chế retry được driver hỗ trợ; tránh giả định lỗi nghĩa là server không làm gì.

**Bước 5 — Retry có kiểm soát.** Chỉ retry thao tác phù hợp với chính sách idempotency; đối với duplicate, so sánh bản ghi hiện có để phân biệt gửi lại cùng dữ liệu với xung đột nghiệp vụ.

**Bước 6 — Đối soát và công bố hoàn tất.** Số bản ghi chuẩn trong database phải phù hợp bộ input mong đợi sau khi loại những bản bị từ chối có lý do. Chỉ chuyển trạng thái import sang hoàn tất khi tiêu chí kinh doanh được đáp ứng.

### 13.1. Ví dụ phân loại ba loại kết quả

```text
Input: 6 document
  A: hợp lệ
  B: hợp lệ
  C: trùng unique index
  D: hợp lệ
  E: sai schema
  F: hợp lệ

Nếu ordered=true:
  Có thể ghi A, B; dừng tại C; D/E/F chưa được thử.

Nếu ordered=false:
  Có thể ghi A, B, D, F; C và E báo write errors.
  Thứ tự xử lý không có hợp đồng giống danh sách ban đầu.

Nếu có lỗi mạng/timeout:
  Không suy ra kết quả chỉ từ danh sách input; cần readback/đối soát.
```

Ví dụ mô tả nguyên tắc của write errors xử lý trên server. Một số lỗi phát hiện ở driver trước khi gửi có thể làm cả lời gọi thất bại trước khi các thao tác được thử.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “`insertMany()` là một transaction.” | Insert nhiều document ngoài transaction có thể thành công một phần. |
| “`ordered: true` gặp lỗi sẽ rollback các document trước đó.” | Thao tác thành công trước lỗi vẫn tồn tại nếu không có transaction rollback. |
| “`ordered: false` bỏ qua lỗi nên luôn trả success.” | API vẫn có thể báo exception và cung cấp danh sách lỗi một phần. |
| “Unordered luôn chạy song song và luôn nhanh hơn.” | Nó chỉ cho phép tối ưu; hiệu năng phụ thuộc topology, tải, index và write concern. |
| “Ordered bảo đảm `find()` trả theo thứ tự insert.” | Muốn thứ tự query rõ ràng phải dùng `sort()`. |
| “Retry cả `insertMany()` an toàn nếu client timeout.” | Có thể có bản ghi đã được ghi; cần ID ổn định và đối soát. |
| “Trùng `_id` khi retry luôn là thành công.” | Phải kiểm tra bản ghi tồn tại tương đương payload/ý nghĩa nghiệp vụ. |
| “Một document vượt 16 MiB sẽ tự được MongoDB chia nhỏ.” | Phải đổi mô hình lưu trữ hoặc cơ chế lưu tệp phù hợp. |
| “`bulkWrite()` ordered bảo đảm tất cả operation nguyên tử.” | Ordered chỉ là thứ tự/dừng lỗi; atomicity toàn tập cần cơ chế khác. |
| “Unordered phù hợp cho mọi danh sách thao tác.” | Không nên dùng khi các thao tác cần phụ thuộc tuần tự. |

## 15. Bài tập vận dụng

### Bài 1 — Quan sát ordered và unordered

Tạo hai collection thử `testOrdered` và `testUnordered`, mỗi collection có sẵn document `{ _id: "existing" }`. Với cùng mảng `[A, existing, B, C]`, gọi `insertMany()` một lần với `ordered: true` và một lần với `false`. Dự đoán trước những ID còn lại rồi xác nhận bằng `find().sort({ _id: 1 })`.

### Bài 2 — Duplicate email trong dữ liệu import

Collection `customers` có unique index trên `emailNormalized`. Một file CSV có 50.000 dòng và 200 email đã tồn tại. Thiết kế nhập theo batch, chọn ordered/unordered, cách lưu danh sách lỗi và điều kiện nào cho phép xem duplicate là “đã nhập trước đó” thay vì báo xung đột.

### Bài 3 — Bulk thao tác phụ thuộc

Trong `bulkWrite()`, thao tác đầu insert `{ _id: "task-1", status: "NEW" }`, thao tác sau update status thành `READY`. Hãy giải thích khác biệt của `ordered: true` và `false`; nếu cần cả hai hoặc không gì cả, bạn dùng cơ chế gì?

### Bài 4 — Retry sau timeout

Client gửi 1.000 event, nhận network timeout và không biết server đã ghi tới đâu. Mỗi event có ID duy nhất từ upstream. Hãy thiết kế bước xác nhận ID đã tồn tại, retry những ID cần thiết, xử lý trùng ID nhưng khác payload và checkpoint cho job.

### Bài 5 — Đánh giá hiệu năng đúng cách

Chạy ingest dữ liệu tương tự với cùng index, cùng write concern và cùng khối lượng, một lượt ordered và một lượt unordered, trong môi trường thử có giám sát. Đo số record thành công/s, lỗi, p95 latency và disk/CPU. Vì sao thời gian total của lượt ordered dừng tại lỗi sớm không thể dùng để kết luận nhanh hơn unordered hoàn tất nhiều insert hơn?

## Kết luận

**`ordered: true`** giữ thứ tự thao tác và dừng khi gặp write error; **`ordered: false`** cho phép tiếp tục những thao tác độc lập và có thể giúp tăng throughput trong những môi trường phù hợp. Cả hai đều có thể để lại **kết quả ghi một phần** ngoài transaction; chúng cũng không quyết định thứ tự đọc của `find()`.

Khi ghi nhiều document, hãy chọn chế độ dựa trên **phụ thuộc thứ tự và khả năng chấp nhận lỗi một phần**, đồng thời thiết kế ID ổn định, unique index, validation, retry và đối soát. Với yêu cầu tất cả hoặc không gì cả, cần transaction ở ranh giới nghiệp vụ phù hợp. Một batch thành công về mặt API chỉ có ý nghĩa khi ứng dụng hiểu được chính xác **document nào đã được ghi, document nào thất bại và điều kiện nào cần thử lại**.

