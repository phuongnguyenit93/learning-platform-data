# Ordered, unordered và cách đọc kết quả hoặc lỗi của bulkWrite trong MongoDB

## Mục tiêu bài học

Trong MongoDB, `bulkWrite()` cho phép gom nhiều thao tác ghi vào một lời gọi. Các thao tác này có thể là thêm, cập nhật, thay thế hoặc xóa document. Hai chế độ quan trọng là **ordered** và **unordered**, quyết định cách MongoDB xử lý thứ tự và tiếp tục khi xuất hiện write error.

Sau bài học, người học có thể:

- Sử dụng sáu loại thao tác trong collection-level `bulkWrite()`.
- Phân biệt `ordered: true` (mặc định) và `ordered: false`.
- Đọc số liệu `insertedCount`, `matchedCount`, `modifiedCount`, `deletedCount`, `upsertedCount` và các ID map.
- Phân biệt **write error**, **write concern error** và lỗi command/network.
- Phân tích **partial success**, đối chiếu vị trí lỗi với operation gốc và xử lý retry an toàn.
- Thiết kế bulk cho import, đồng bộ hoặc xóa dữ liệu với business key, index và checkpoint phù hợp.
- Hiểu vì sao bulkWrite không tự động có ngữ nghĩa transaction và không thay thế postcondition nghiệp vụ.

> **Ghi nhớ:** Ordered có thể dừng ở write error đầu tiên, unordered có thể tiếp tục các thao tác độc lập, nhưng **cả hai đều có thể thành công một phần**. Một phản hồi không có lỗi cũng chưa chứng minh mọi update/delete đã tác động đến số document mà nghiệp vụ mong đợi.

---

## 1. Bulk write khác nhiều lệnh riêng lẻ như thế nào?

Một ứng dụng đồng bộ 1.000 sản phẩm có thể gọi 1.000 lần `updateOne()`, hoặc gửi danh sách operations qua `bulkWrite()`. Gom operations có thể giảm overhead giao tiếp client–server và tạo một điểm xử lý kết quả tập trung.

Cú pháp trong mongosh:

~~~javascript
db.products.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "SKU-01", name: "Bàn phím", stock: 10 }
      }
    },
    {
      updateOne: {
        filter: { _id: "SKU-02" },
        update: { $set: { stock: 20 } }
      }
    },
    {
      deleteOne: {
        filter: { _id: "TEMP-01" }
      }
    }
  ],
  { ordered: true }
);
~~~

Tốc độ thực tế vẫn phụ thuộc index, write concern, server load, loại operation, kích thước batch, network và concurrency. Bulk không biến những filter không có index thành truy vấn nhanh.

**Phạm vi:** Bài dùng API **`db.collection.bulkWrite()`**, mọi operation thuộc **một collection**. Các MongoDB/driver phiên bản mới có thể có API cấp client hỗ trợ nhiều namespace, nhưng cú pháp và kết quả khác; không đánh đồng.

## 2. Sáu operation thường gặp

| Loại | Mục đích | Các thuộc tính chính |
|---|---|---|
| `insertOne` | Thêm một document | `document` |
| `updateOne` | Cập nhật tối đa một document | `filter`, `update`, có thể `upsert` |
| `updateMany` | Cập nhật mọi document khớp | `filter`, `update` |
| `replaceOne` | Thay một document khớp | `filter`, `replacement` |
| `deleteOne` | Xóa tối đa một document | `filter` |
| `deleteMany` | Xóa mọi document khớp | `filter` |

Ví dụ đầy đủ:

~~~javascript
db.inventory.bulkWrite(
  [
    {
      insertOne: {
        document: {
          _id: "P-100",
          name: "Tai nghe",
          stock: 100
        }
      }
    },
    {
      updateOne: {
        filter: { _id: "P-101" },
        update: { $set: { status: "ACTIVE" } }
      }
    },
    {
      updateMany: {
        filter: { category: "LEGACY" },
        update: { $set: { archived: true } }
      }
    },
    {
      replaceOne: {
        filter: { _id: "P-102" },
        replacement: {
          _id: "P-102",
          name: "Chuột",
          stock: 25
        }
      }
    },
    {
      deleteOne: {
        filter: { _id: "TEMP-1" }
      }
    },
    {
      deleteMany: {
        filter: { expired: true, archived: true }
      }
    }
  ],
  { ordered: true }
);
~~~

Cần hiểu:

- `replaceOne` thay document theo replacement; các field cũ không nằm trong replacement có thể mất.
- Một `updateMany` có thể matched nhiều document, dù chỉ là **một operation**.
- `deleteMany` với filter rỗng có thể xóa toàn collection.
- Một operation không tìm document phù hợp có thể hoàn thành bình thường với matched/deleted count bằng 0.
- `upsert: true` có thể tạo document mới khi filter không khớp; chỉ dùng nếu nghiệp vụ cho phép tạo mới.

---

## 3. Ordered: xử lý tuần tự và dừng sau write error

Nếu không truyền `ordered`, collection-level bulkWrite sử dụng `ordered: true`.

~~~javascript
db.collectionName.bulkWrite(operations, { ordered: true });
~~~

Ngữ nghĩa:

1. Các operation được xử lý theo thứ tự xuất hiện trong mảng.
2. Khi gặp một **write error**, các operation tiếp theo dừng theo ngữ nghĩa ordered.
3. Các operation thành công trước lỗi **không bị tự động rollback**.
4. Một operation matched 0 không phải write error nên không tự làm dừng batch.

Minh họa:

~~~text
Index 0: INSERT A        -> thành công
Index 1: INSERT trùng ID -> write error
Index 2: INSERT B        -> không chạy
Index 3: UPDATE C        -> không chạy

A đã ghi vẫn có thể tồn tại.
~~~

Ordered phù hợp khi operation sau phụ thuộc thao tác trước, hoặc job muốn dừng sớm khi một operation sai. Nhưng nó không tự kiểm tra điều kiện nghiệp vụ.

Ví dụ:

~~~javascript
db.workflows.bulkWrite(
  [
    {
      updateOne: {
        filter: { _id: "TASK-1", status: "READY" },
        update: { $set: { status: "RUNNING" } }
      }
    },
    {
      updateOne: {
        filter: { _id: "TASK-1" },
        update: { $set: { owner: "worker-A" } }
      }
    }
  ],
  { ordered: true }
);
~~~

Nếu operation đầu matched 0, operation sau **vẫn có thể chạy**. Nếu cần “chỉ thay owner khi status đang READY”, hãy gộp các field vào một update với filter chung:

~~~javascript
db.workflows.updateOne(
  { _id: "TASK-1", status: "READY" },
  {
    $set: {
      status: "RUNNING",
      owner: "worker-A"
    }
  }
);
~~~

Một update trên cùng document có tính nguyên tử, phù hợp hơn chuỗi hai update phụ thuộc khi có thể gộp.

## 4. Unordered: không bảo đảm thứ tự, tiếp tục ghi độc lập

~~~javascript
db.collectionName.bulkWrite(operations, { ordered: false });
~~~

Ngữ nghĩa:

1. **Không được suy ra thứ tự thực thi** từ vị trí operation trong mảng.
2. Một write error không mặc nhiên ngăn các operations độc lập khác được xử lý.
3. Bulk có thể trả **exception** dù nhiều operation khác thành công.
4. Không có cam kết thực thi song song hoặc nhanh hơn trong mọi workload.
5. Lỗi cấp command, kết nối hay hệ thống có thể khiến kết quả không đầy đủ, không bảo đảm mọi operation được thử.

Minh họa:

~~~text
Index 0: INSERT A        -> có thể thành công
Index 1: INSERT trùng ID -> write error
Index 2: INSERT B        -> có thể thành công

Unordered có thể partial success.
Thứ tự thời gian thực tế không được bảo đảm.
~~~

Unordered phù hợp cho import hoặc upsert nhiều record độc lập, có business key và cơ chế đối soát/retry. Nó **không phù hợp** cho một chuỗi operations mà bước sau cần dữ liệu do bước trước tạo.

### 4.1. Bảng so sánh

| Tiêu chí | Ordered | Unordered |
|---|---|---|
| Option | `ordered: true` | `ordered: false` |
| Mặc định | Có | Không |
| Thứ tự | Theo mảng | Không bảo đảm |
| Write error | Dừng các operations tiếp theo | Có thể tiếp tục các operations độc lập |
| Kết quả trước lỗi | Có thể đã lưu | Có thể đã lưu |
| Atomic toàn bulk | **Không** | **Không** |
| Operations phụ thuộc nhau | Có thể phù hợp về thứ tự | Nên tránh |
| Ops độc lập | Dùng được | Phù hợp |
| Throughput | Tùy workload | Có thể tốt hơn, không bảo đảm |
| Error handling | Vị trí lỗi và partial result | Nhiều vị trí lỗi và partial result |

### 4.2. Cạm bẫy: phụ thuộc mà matched 0 không báo lỗi

~~~javascript
const ops = [
  {
    insertOne: {
      document: { _id: "DOC-1", status: "CREATED" }
    }
  },
  {
    updateOne: {
      filter: { _id: "DOC-1" },
      update: { $set: { status: "READY" } }
    }
  }
];
~~~

Với unordered, update có thể chạy trước insert, matched 0. Sau đó insert tạo document ở trạng thái CREATED. **Không có write error nhưng trạng thái nghiệp vụ sai**. Giải pháp: gộp thành insert trạng thái READY, hoặc dùng ordered/transaction khi có lý do thực sự cần nhiều bước.

---

## 5. Thực hành ordered với duplicate key

Các lệnh dưới đây chỉ dùng trong database lab. Nếu chạy lại, phải dùng tên collection mới hoặc dọn dữ liệu thử nghiệm có chủ đích; không drop dữ liệu production.

~~~javascript
use bulk_lab

db.ordered_products.insertOne({
  _id: "EXISTING-01",
  name: "Đã tồn tại"
});
~~~

Khóa `_id` có tính duy nhất trong collection theo quy tắc MongoDB. Thử insert trùng thường gây mã lỗi **11000**.

~~~javascript
const orderedOps = [
  {
    insertOne: {
      document: { _id: "NEW-01", name: "Sản phẩm A" }
    }
  },
  {
    insertOne: {
      document: { _id: "EXISTING-01", name: "Trùng ID" }
    }
  },
  {
    insertOne: {
      document: { _id: "NEW-02", name: "Sản phẩm B" }
    }
  }
];

try {
  printjson(
    db.ordered_products.bulkWrite(
      orderedOps,
      { ordered: true }
    )
  );
} catch (error) {
  print(error.message);
}
~~~

Quan sát trạng thái:

~~~javascript
db.ordered_products
  .find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
~~~

Khi không có lỗi khác:

- Index 0 insert NEW-01 thành công.
- Index 1 trùng EXISTING-01, sinh write error.
- Index 2 không được thực hiện.
- NEW-01 vẫn tồn tại dù bulk có lỗi.
- NEW-02 chưa có.

Đây là ví dụ về **dừng theo thứ tự nhưng không rollback tự động**.

## 6. Thực hành unordered với cùng lỗi

Dùng collection riêng:

~~~javascript
db.unordered_products.insertOne({
  _id: "EXISTING-01",
  name: "Đã tồn tại"
});

const unorderedOps = [
  {
    insertOne: {
      document: { _id: "NEW-01", name: "Sản phẩm A" }
    }
  },
  {
    insertOne: {
      document: { _id: "EXISTING-01", name: "Trùng ID" }
    }
  },
  {
    insertOne: {
      document: { _id: "NEW-02", name: "Sản phẩm B" }
    }
  }
];

try {
  printjson(
    db.unordered_products.bulkWrite(
      unorderedOps,
      { ordered: false }
    )
  );
} catch (error) {
  print(error.message);
}
~~~

Quan sát:

~~~javascript
db.unordered_products
  .find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
~~~

Trong lab không có lỗi khác, hai insert độc lập NEW-01/NEW-02 có thể đều thành công, còn insert trùng vẫn lỗi. Lời gọi vẫn có thể trả exception do có operation lỗi.

**Vì sao chuẩn bị ID trùng trước batch?** Nếu hai operations unordered cùng cố insert một ID chưa tồn tại, không thể dựa vào vị trí mảng để nói insert nào thắng. Chuẩn bị sẵn ID trùng giúp kiểm tra đúng sự khác biệt về hành vi tiếp tục sau lỗi.

---

## 7. Cách đọc kết quả thành công

Ví dụ minh họa hình dạng kết quả, **không phải output của batch lab cụ thể**:

~~~javascript
{
  acknowledged: true,
  insertedCount: 2,
  matchedCount: 3,
  modifiedCount: 2,
  deletedCount: 1,
  upsertedCount: 1,
  insertedIds: {
    "0": "NEW-01",
    "4": "NEW-02"
  },
  upsertedIds: {
    "2": "SKU-201"
  }
}
~~~

Một số driver/version biểu diễn ID và metadata khác nhau; hãy xem định nghĩa API của môi trường thực tế.

| Trường | Ý nghĩa |
|---|---|
| `acknowledged` | Operation được xác nhận theo write concern được yêu cầu hay không |
| `insertedCount` | Số document được insert từ insert operations |
| `matchedCount` | Tổng số document khớp update/replace operations |
| `modifiedCount` | Tổng số document thực sự thay đổi |
| `deletedCount` | Số document đã xóa |
| `upsertedCount` | Số document tạo mới bởi upsert |
| `insertedIds` | ID của inserts, thường gắn với vị trí operation |
| `upsertedIds` | ID của upserts, thường gắn với vị trí operation |

### 7.1. Bộ đếm là số document, không phải số operations

Một `updateMany` là một operation nhưng có thể cập nhật 100 document; một `deleteMany` có thể xóa 500 document. Vì vậy không thể dùng tổng các counters như một công thức tổng quát tính số operations thành công.

### 7.2. Matched khác modified

~~~javascript
db.count_demo.insertOne({
  _id: "A",
  status: "ACTIVE"
});

const result = db.count_demo.bulkWrite([
  {
    updateOne: {
      filter: { _id: "A" },
      update: { $set: { status: "ACTIVE" } }
    }
  }
]);

printjson(result);
~~~

Document matched nhưng giá trị không thay đổi, nên có thể nhận:

~~~text
matchedCount = 1
modifiedCount = 0
~~~

Đó không phải write error.

Tương tự, một `deleteOne` không tìm document có thể hoàn thành bình thường với `deletedCount: 0`.

### 7.3. Upsert đếm riêng

~~~javascript
db.count_demo.bulkWrite([
  {
    updateOne: {
      filter: { _id: "B" },
      update: {
        $set: { status: "ACTIVE" },
        $setOnInsert: { source: "import" }
      },
      upsert: true
    }
  }
]);
~~~

Nếu B chưa có, `upsertedCount` tăng và ID xuất hiện trong upserted IDs; không chỉ nhìn `insertedCount` để xác định số document mới tạo.

### 7.4. Map ID theo vị trí input

~~~javascript
const ops = [
  { insertOne: { document: { _id: "A" } } }, // index 0
  {
    updateOne: {
      filter: { _id: "B" },
      update: { $set: { x: 1 } }
    }
  }, // index 1
  { insertOne: { document: { _id: "C" } } } // index 2
];
~~~

`insertedIds` có thể có index 0 và 2. Đừng coi chúng là “hai insert thứ 0 và 1” mà mất liên hệ đến mảng gốc.

### 7.5. Unacknowledged write

Nếu dùng write concern không chờ acknowledgment, caller không thể dựa vào cùng mức thống kê hoặc xác nhận như acknowledged writes. Với job import cần đối soát, nên dùng write concern phù hợp.

---

## 8. Khi bulkWrite trả lỗi: ba nhóm cần phân biệt

### 8.1. Write error của một operation

Ví dụ error metadata có thể gồm:

~~~javascript
{
  index: 1,
  code: 11000,
  errmsg: "E11000 duplicate key error ..."
}
~~~

Đây là **ví dụ hình dạng thông tin**, không phải schema exception được bảo đảm cho mọi shell/driver/version.

| Thuộc tính | Cách dùng |
|---|---|
| `index` | Vị trí operation lỗi trong input, thường tính từ 0 |
| `code` | Mã lỗi MongoDB |
| `errmsg` / `message` | Mô tả lỗi |
| `op` hoặc chi tiết tương đương | Thông tin operation nếu API trả |
| Partial result | Các ghi đã được xác nhận thành công đến đâu, nếu có |

Mã phổ biến:

- **11000:** duplicate key, chẳng hạn trùng `_id` hoặc unique index.
- **121:** document validation failure.
- Lỗi update path: field hoặc đường dẫn không hợp lệ/xung đột.
- Lỗi quyền: user không được phép thực hiện operation.
- Lỗi giới hạn: document/message vượt kích thước hỗ trợ.

Không bắt mọi exception rồi coi là duplicate key có thể bỏ qua.

### 8.2. Write concern error không giống write error

Ví dụ yêu cầu majority:

~~~javascript
db.catalog.bulkWrite(
  operations,
  {
    ordered: false,
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

Nếu primary đã xử lý ghi nhưng majority chưa xác nhận trước timeout, caller có thể nhận write concern error. Điều này **không chứng minh ghi chưa xảy ra**. Trạng thái có thể chưa chắc chắn theo tiêu chí xác nhận yêu cầu.

Cần đối soát theo ID nghiệp vụ, kiểm tra replica set, replication lag và chính sách retry. Lặp lại nguyên batch chứa `$inc` có thể gây sai số.

### 8.3. Network/command error có thể làm trạng thái không rõ

Nếu client gửi bulk rồi mất kết nối trước response, server có thể đã hoàn thành một phần hoặc toàn bộ. Không suy ra “không nhận được response = không có ghi nào”.

Lỗi cấp command hoặc hệ thống nghiêm trọng có thể chặn cả việc xử lý những operations tiếp theo trong unordered; nguyên tắc “tiếp tục sau write error” không phải bảo đảm cho mọi loại lỗi.

---

## 9. Bắt lỗi trong mongosh và đối chiếu operation index

~~~javascript
const records = [
  { sourceKey: "IMP-100", sku: "SKU-100", name: "A" },
  { sourceKey: "IMP-101", sku: "SKU-101", name: "B" },
  { sourceKey: "IMP-102", sku: "SKU-102", name: "C" }
];

const ops = records.map((record) => ({
  updateOne: {
    filter: { sku: record.sku },
    update: {
      $set: { name: record.name },
      $setOnInsert: { sourceKey: record.sourceKey }
    },
    upsert: true
  }
}));

try {
  const result = db.catalog.bulkWrite(
    ops,
    { ordered: false }
  );
  printjson(result);
} catch (error) {
  print(error.message);

  // Thuộc tính thật phụ thuộc môi trường mongosh/driver.
  if (error.writeErrors) {
    printjson(error.writeErrors);
  }
  if (error.writeConcernErrors) {
    printjson(error.writeConcernErrors);
  }
  if (error.result) {
    printjson(error.result);
  }
}
~~~

Nếu một write error có `index: 1`, bản ghi nguồn tương ứng là:

~~~javascript
records[1];
// { sourceKey: "IMP-101", sku: "SKU-101", name: "B" }
~~~

Chỉ dùng các trường trên exception **khi chúng tồn tại**. Một số môi trường biểu diễn danh sách lỗi, kết quả từng phần hoặc write concern errors bằng method/property khác. Network error có thể không có partial result. Phải xem hợp đồng của driver đang dùng.

Dữ liệu dùng để log nên gồm `batchId`, operation index, business key, error code; không ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm.

---

## 10. Idempotency và retry có kiểm soát

### 10.1. Operation idempotent

Một operation idempotent khi chạy lại cùng yêu cầu không tạo tác dụng ngoài ý định.

Tương đối phù hợp khi retry:

~~~javascript
{
  updateOne: {
    filter: { _id: "P-1" },
    update: { $set: { status: "ACTIVE" } }
  }
}
~~~

Nếu không có writer cạnh tranh hay side effect khác, chạy lại vẫn đưa `status` về ACTIVE.

Không idempotent:

~~~javascript
{
  updateOne: {
    filter: { _id: "P-1" },
    update: { $inc: { stock: 1 } }
  }
}
~~~

Nếu lần đầu đã ghi nhưng response bị mất, retry có thể tăng stock lần hai.

### 10.2. Upsert và khóa nghiệp vụ

~~~javascript
db.catalog.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_catalog_sku" }
);
~~~

Một import có thể dùng updateOne/upsert theo từng SKU:

~~~javascript
db.catalog.bulkWrite(
  [
    {
      updateOne: {
        filter: { sku: "SKU-A" },
        update: {
          $set: { name: "A", price: 120000 },
          $setOnInsert: { source: "import" }
        },
        upsert: true
      }
    },
    {
      updateOne: {
        filter: { sku: "SKU-B" },
        update: {
          $set: { name: "B", price: 85000 },
          $setOnInsert: { source: "import" }
        },
        upsert: true
      }
    }
  ],
  { ordered: false }
);
~~~

Các SKU khác nhau là operations độc lập. Unique index giảm rủi ro bản ghi trùng, nhưng hai writer cùng upsert một SKU vẫn có thể tranh chấp và gặp duplicate key trong một số điều kiện.

### 10.3. Không retry mù

| Lỗi | Cách tiếp cận |
|---|---|
| Duplicate key 11000 | Đọc document hiện tại, kiểm tra dữ liệu có đúng yêu cầu không |
| Validation 121 | Sửa input/schema theo quy trình |
| Thiếu quyền | Điều chỉnh quyền phù hợp, không tăng quyền tùy tiện |
| Write concern timeout | Đối soát trạng thái trước retry |
| Network timeout | Dùng business key/request ID và kiểm tra ghi đã diễn ra chưa |
| Update matched 0 | Đánh giá filter và trạng thái nghiệp vụ, không tự coi là lỗi transport |

Driver có thể có cơ chế retryable writes theo những điều kiện riêng. Không mặc định mọi kiểu bulk và mọi operation tự được retry an toàn.

---

## 11. BulkWrite và transaction

### 11.1. Không phải một đơn vị nguyên tử

MongoDB có atomicity ở cấp thao tác trên **một document**; bulk thông thường gồm nhiều operations **không tự tạo transaction toàn batch**.

~~~text
bulkWrite:
  insert A -> thành công
  insert B -> thành công
  update C -> write error
  delete D -> tùy ordered/unordered và loại lỗi

Không có transaction:
  A và B có thể vẫn tồn tại.
  Lỗi C không tự undo A/B.
~~~

Tương tự, một `updateMany` tác động nhiều document không tự bảo đảm cập nhật nguyên tử toàn bộ tập.

### 11.2. Bulk bên trong transaction

MongoDB hỗ trợ multi-document transactions theo phiên bản và topology phù hợp. Khi gọi bulk trong transaction, phải xét **commit/abort của transaction** chứ không áp dụng máy móc semantics partial success của bulk bên ngoài transaction. Write failure có thể khiến transaction bị abort; unordered không phải cơ chế “bỏ qua lỗi để commit phần tốt”.

Transaction có chi phí tài nguyên, conflict/retry và giới hạn thực thi. Không mặc định bọc một import lớn nhiều giờ trong một transaction để lấy all-or-nothing; cân nhắc batch checkpoint và idempotency.

---

## 12. Java Sync Driver: cách đọc kết quả hoặc ngoại lệ

Java Sync Driver có `MongoCollection.bulkWrite` nhận `List<WriteModel<T>>` và `BulkWriteOptions`.

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;
import com.mongodb.bulk.BulkWriteResult;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.DeleteOneModel;
import com.mongodb.client.model.InsertOneModel;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public class BulkExample {

    public static void run(MongoCollection<Document> collection) {

        List<WriteModel<Document>> ops = Arrays.asList(
            new InsertOneModel<>(
                new Document("_id", "SKU-501")
                    .append("name", "Bàn phím")
            ),
            new UpdateOneModel<>(
                eq("_id", "SKU-502"),
                set("status", "ACTIVE")
            ),
            new DeleteOneModel<>(
                eq("_id", "TEMP-501")
            )
        );

        try {
            BulkWriteResult result = collection.bulkWrite(
                ops,
                new BulkWriteOptions().ordered(false)
            );

            System.out.println(
                "Inserted: " + result.getInsertedCount()
            );
            System.out.println(
                "Matched: " + result.getMatchedCount()
            );
            System.out.println(
                "Modified: " + result.getModifiedCount()
            );
            System.out.println(
                "Deleted: " + result.getDeletedCount()
            );
            System.out.println(
                "Upserts: " + result.getUpserts().size()
            );

        } catch (MongoBulkWriteException error) {
            for (BulkWriteError failure : error.getWriteErrors()) {
                System.err.println(
                    "Index=" + failure.getIndex()
                    + ", code=" + failure.getCode()
                    + ", message=" + failure.getMessage()
                );
            }

            BulkWriteResult partial = error.getWriteResult();

            if (partial != null && partial.wasAcknowledged()) {
                System.err.println(
                    "Partial inserted=" + partial.getInsertedCount()
                    + ", modified=" + partial.getModifiedCount()
                    + ", deleted=" + partial.getDeletedCount()
                );
            }

            if (error.getWriteConcernError() != null) {
                System.err.println(
                    "Write concern error="
                    + error.getWriteConcernError().getMessage()
                );
            }
        }
    }
}
~~~

Đây là ví dụ dùng API phổ biến; `collection` giả định đã được kết nối. Các package/method và khả năng báo lỗi cụ thể phụ thuộc phiên bản Java Driver; kiểm tra documentation của dự án. Không phải mọi lỗi mạng/command đều là `MongoBulkWriteException`, nên production code cần xử lý thêm các exception khác.

Map lỗi về nguồn:

~~~java
List<String> businessIds = Arrays.asList(
    "SKU-501",
    "SKU-502",
    "TEMP-501"
);

int index = failure.getIndex();

if (index >= 0 && index < businessIds.size()) {
    String businessKey = businessIds.get(index);
    System.err.println("Failed key=" + businessKey);
}
~~~

Khi một driver chia batch lớn, vẫn phải theo **hợp đồng index của API** và giữ business key để đối soát.

---

## 13. Báo cáo import có partial success

Một job import có thể định nghĩa DTO:

~~~json
{
  "batchId": "product-import-20261114-001",
  "requestedOperations": 1000,
  "ordered": false,
  "state": "PARTIAL_SUCCESS",
  "reported": {
    "insertedCount": 700,
    "matchedCount": 200,
    "modifiedCount": 190,
    "deletedCount": 0,
    "upsertedCount": 85
  },
  "errors": [
    {
      "operationIndex": 15,
      "businessKey": "SKU-101",
      "code": 11000,
      "category": "DUPLICATE_KEY"
    }
  ],
  "reconciliationRequired": true
}
~~~

**Đây là schema báo cáo do ứng dụng tự thiết kế**, không phải raw MongoDB response. Số liệu chỉ minh họa, không tương ứng với một batch thực cụ thể.

Trạng thái có thể là:

| Trạng thái | Ý nghĩa |
|---|---|
| `COMPLETED` | Tất cả yêu cầu được xác nhận và hậu điều kiện đúng |
| `PARTIAL_SUCCESS` | Một phần thành công, một phần lỗi |
| `FAILED` | Không có kết quả hoàn thành được xác nhận hoặc job không thể chạy |
| `UNKNOWN_REQUIRES_RECONCILIATION` | Thiếu bằng chứng chắc chắn do lỗi network/write concern |
| `VALIDATION_REJECTED` | Input bị từ chối trước khi gửi bulk |

Nên ghi batch ID, bản ghi nguồn, phiên bản logic, ordered flag, write concern, counters, error index/code, business key và trạng thái đối soát.

**Không dùng** `insertedCount + matchedCount + deletedCount` làm tổng số operations thành công một cách tổng quát: `updateMany` và `deleteMany` có thể tác động nhiều document, đồng thời các counters không đo cùng đơn vị công việc.

### 13.1. Quy trình đối soát

1. Lưu danh sách operation gốc hoặc một tham chiếu bất biến theo batch ID.
2. Đọc write errors với index và error code.
3. Đọc partial result khi API cung cấp.
4. Phân biệt các operations không chạy do ordered với các operations không rõ vì mất kết nối.
5. Truy vấn theo business key để kiểm tra ghi đã diễn ra chưa.
6. Chỉ retry những operations đủ điều kiện an toàn.
7. Đánh dấu hoàn tất khi các hậu điều kiện nghiệp vụ được xác minh.

---

## 14. Batch size và hiệu năng

Bulk không tự sửa vấn đề filter không có index. Ví dụ hàng nghìn update theo `sku` nên có index:

~~~javascript
db.catalog.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_catalog_sku" }
);
~~~

Trước khi tạo unique index, phải xử lý dữ liệu trùng trong collection.

MongoDB giới hạn kích thước BSON document (thông thường **16 MiB**) và các giới hạn về message/batch. Driver có thể tự chia một bulk lớn thành nhiều nhóm phù hợp. Không giữ hàng triệu operations trong memory mà chưa đánh giá:

- RAM của client.
- Kích thước request/error response.
- Mức write pressure, index maintenance, network, replication lag.
- Khả năng resume/retry từng nhóm.
- Throughput và p95/p99 latency dưới tải.
- Rủi ro khi một operation xóa hoặc cập nhật rất nhiều document.

Nên dùng batch có kích thước **đo được**, checkpoint, ID ổn định và cơ chế tiếp tục sau lỗi. Unordered có thể nhanh hơn với independent writes, nhưng không bảo đảm; benchmark phải dùng cùng dữ liệu, index, write concern, concurrency và error rate.

### 14.1. Đặc biệt thận trọng với xóa hàng loạt

Ví dụ xóa session hết hạn:

~~~javascript
db.sessions.bulkWrite(
  [
    {
      deleteMany: {
        filter: {
          status: "CLOSED",
          expiresAt: {
            $lt: ISODate("2026-11-01T00:00:00Z")
          }
        }
      }
    }
  ],
  { ordered: true }
);
~~~

Trước khi ghi, hãy chạy `countDocuments` với cùng filter, lấy mẫu dữ liệu, kiểm tra index, tenant scope, backup và kế hoạch restore:

~~~javascript
db.sessions.countDocuments({
  status: "CLOSED",
  expiresAt: {
    $lt: ISODate("2026-11-01T00:00:00Z")
  }
});
~~~

`deleteMany: {filter:{}}` có thể xóa mọi document. Nó có thể là một operation hợp lệ về cú pháp và hoàn thành không có write error, dù gây hậu quả nghiệp vụ nghiêm trọng.

---

## 15. Tình huống thực tế

### A. Import có duplicate key

Batch gồm 1.000 insert độc lập và một insert trùng khóa.

- Ordered: dừng ở write error đầu.
- Unordered: những insert độc lập khác có thể vẫn thành công.
- Hành động: đọc index lỗi, xác minh document hiện có và báo cáo partial success.

### B. Cập nhật không trúng document

Một updateOne có filter quá chặt và matched 0.

- Không tự sinh write error.
- Ordered vẫn có thể tiếp tục.
- Hành động: kiểm tra postcondition, không coi “không exception” là “đã sửa đúng”.

### C. Vi phạm schema

Một record thiếu field bắt buộc, nhận code 121.

- Cần sửa input/validator theo quy trình.
- Retry nguyên dạng sẽ không giải quyết lỗi.
- Unordered có thể tiếp tục những record khác.

### D. Hai unordered updates cùng document

~~~javascript
const ops = [
  {
    updateOne: {
      filter: { _id: "P-1" },
      update: { $set: { status: "ACTIVE" } }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-1" },
      update: { $set: { status: "INACTIVE" } }
    }
  }
];
~~~

Trạng thái cuối có thể phụ thuộc thứ tự xử lý. Không dùng unordered nếu thứ tự hai update là yêu cầu nghiệp vụ; cân nhắc một operation hoặc điều kiện/versioning phù hợp.

### E. Write concern timeout

Primary có thể đã xử lý ghi nhưng chưa đạt majority trước timeout. Không tự khẳng định chưa ghi; đối soát trạng thái trước retry.

### F. Network mất khi đang gửi batch

Có thể một phần ghi đã xảy ra. Không gửi lại nguyên batch chứa `$inc` hoặc inserts có ID phát sinh mới mà không có cơ chế chống lặp.

### G. Bulk nằm trong transaction

Khi transaction abort, phải xử lý commit/abort theo ngữ nghĩa transaction. Không dựa vào ý tưởng “unordered tiếp tục sau lỗi nên có thể commit phần tốt”.

---

## 16. Hiểu lầm thường gặp

**“Ordered = all-or-nothing.”** Sai. Ghi trước lỗi không tự rollback.

**“Unordered = chạy song song.”** Không có bảo đảm; chỉ không yêu cầu thứ tự.

**“Unordered bỏ qua lỗi và coi toàn batch thành công.”** Sai. Bulk có thể trả exception dù một phần ghi thành công.

**“Một operation = một document.”** Sai đối với updateMany/deleteMany.

**“Matched luôn bằng modified.”** Sai nếu giá trị không thay đổi.

**“Không có exception thì mọi update đều sửa ít nhất một document.”** Sai, filter có thể matched 0.

**“Retry nguyên batch luôn an toàn.”** Sai với `$inc`, side effect hoặc insert thiếu ID ổn định.

**“Duplicate key chứng minh lần trước đã import đúng.”** Không chắc; cần kiểm tra document hiện tại.

**“Write concern error = chưa ghi.”** Sai; có thể đã ghi nhưng chưa đạt mức xác nhận.

**“Error index là thứ tự thực thi của unordered.”** Sai; nó gắn với vị trí operation theo contract API.

**“Chỉ cần log error.message.”** Không đủ để xử lý một import có nhiều records lỗi.

**“Collection bulkWrite cho nhiều collections.”** Không phải cú pháp collection-level trong bài; client-level API đa namespace là trường hợp khác.

---

## 17. Quy trình triển khai an toàn

1. **Liệt kê operations, business keys và sự phụ thuộc.** Nếu một operation dựa vào kết quả của operation trước, tránh unordered.
2. **Kiểm chứng filter và index.** Trước updateMany/deleteMany, đếm và xem mẫu document.
3. **Chọn ordered theo semantics trước tốc độ.** Ordered khi cần tuần tự; unordered khi độc lập.
4. **Thiết kế idempotency.** Dùng unique business key, request ID, `$setOnInsert` khi phù hợp và tránh retry mù.
5. **Chia batch hợp lý.** Kiểm soát memory, server load và lưu checkpoint.
6. **Đọc kết quả.** Dùng counters và ID maps, không chỉ kiểm tra exception.
7. **Phân loại lỗi.** Write error theo index; write concern/network có thể cần đối soát.
8. **Kiểm tra hậu điều kiện.** Dữ liệu cuối phải đúng mục tiêu, kể cả nếu bulk không báo lỗi.
9. **Lưu báo cáo.** Batch ID, counters, errors, business keys, phần còn thiếu và phương án phục hồi.

---

## 18. Bài tập

### Bài 1 — Ordered gặp duplicate key

Trong collection lab, tạo document ID EXISTING. Chạy ordered bulk lần lượt insert A, insert EXISTING, insert B, update A. Dự đoán operation nào chạy, operation nào không. Vì sao A vẫn có thể tồn tại?

### Bài 2 — Unordered với ba insert độc lập

Tạo collection riêng và ID EXISTING. Chạy unordered insert A, insert EXISTING, insert B. Xác minh A/B, lỗi duplicate và index lỗi. Tại sao không nên suy luận thứ tự chạy của A/B?

### Bài 3 — Matched và modified

~~~javascript
db.bulk_counts.insertMany([
  { _id: 1, status: "ACTIVE" },
  { _id: 2, status: "NEW" },
  { _id: 3, status: "NEW" }
]);

db.bulk_counts.bulkWrite([
  {
    updateOne: {
      filter: { _id: 1 },
      update: { $set: { status: "ACTIVE" } }
    }
  },
  {
    updateMany: {
      filter: { status: "NEW" },
      update: { $set: { status: "ACTIVE" } }
    }
  }
]);
~~~

Giải thích vì sao matched khác modified, và cả hai có thể lớn hơn số operations.

### Bài 4 — Upsert

Viết bulk có một insertOne và một updateOne với `upsert: true` tạo mới. Quan sát `insertedCount`, `upsertedCount` và ID maps. Khi chạy lại upsert, kết quả thay đổi thế nào?

### Bài 5 — Operations phụ thuộc

Chạy unordered insert DOC-1 rồi update DOC-1. Nêu hai kết quả có thể tùy thứ tự và viết lại thành một operation duy nhất.

### Bài 6 — Import lỗi một phần

Một batch 500 operations có 12 duplicate key, 3 validation errors và một write concern timeout. Thiết kế DTO báo cáo, cách đối chiếu error index với business key và chiến lược retry cho từng nhóm.

### Bài 7 — Java error handler

Dùng `MongoBulkWriteException` trong Java để đọc `getWriteErrors()`, `getWriteResult()`, `getWriteConcernError()`. Giải thích vì sao vẫn phải xử lý network errors khác.

### Bài 8 — Bulk xóa dữ liệu cũ

Collection sessions có hàng chục triệu document. Chỉ xóa session CLOSED quá hạn 90 ngày. Xác định filter, index, count/sample trước xóa, batch size, checkpoint, backup và báo cáo deletedCount. Cách xử lý nếu filter sai là gì?

---

## 19. Câu hỏi ôn tập

1. Sáu loại operation trong collection-level bulkWrite là gì?
2. Giá trị ordered mặc định là gì?
3. Ordered dừng sau lỗi nào và ghi trước lỗi có rollback không?
4. Unordered có cam kết chạy song song không?
5. Vì sao matched 0 không tự làm ordered dừng?
6. Matched và modified khác nhau thế nào?
7. Vì sao một updateMany có thể tăng matched nhiều đơn vị?
8. Upsert được tính vào trường nào?
9. `writeErrors[].index` giúp xử lý batch như thế nào?
10. Mã 11000 và 121 thường là gì?
11. Write concern error khác write error thế nào?
12. Vì sao network error có thể khiến trạng thái không rõ?
13. Khi nào unordered không phù hợp?
14. Bulk thông thường có nguyên tử toàn batch không?
15. Vì sao retry `$inc` có thể làm sai dữ liệu?
16. Duplicate key có tự chứng minh bản ghi hiện có đúng không?
17. Vì sao không thể tính số operations thành công bằng tổng document counters?
18. Những thông tin gì nên có trong báo cáo partial success?
19. Tại sao bulk deleteMany vẫn cần filter validation và backup?
20. Nếu batch có transaction, phải đánh giá điều kiện commit/abort ra sao?

## 20. Tổng kết

**`bulkWrite()`** hữu ích khi cần ghi nhiều document theo lô, nhưng thành công cần được đánh giá ở cả cấp operation và nghiệp vụ:

- **`ordered: true`:** xử lý theo thứ tự và dừng sau write error; ghi đã hoàn tất không tự rollback.
- **`ordered: false`:** không bảo đảm thứ tự, có thể tiếp tục các operations độc lập sau write error; không biến batch thành success toàn phần.
- **Kết quả:** đọc inserted/matched/modified/deleted/upserted counts và ID maps đúng đơn vị document.
- **Lỗi:** phân biệt write errors theo index, write concern errors và lỗi network/command; đối soát khi trạng thái không chắc chắn.
- **An toàn:** dùng unique key, index, filter chặt, idempotency, checkpoint và chính sách backup/restore.

Một bulk tốt không chỉ nhanh; nó còn giúp trả lời chính xác **đã ghi được gì, lỗi ở đâu và tiếp tục thế nào mà không nhân đôi hoặc mất dữ liệu**.

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Write Operations Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Java Sync Driver — Bulk Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/)
- [MongoDB Manual — db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/)
