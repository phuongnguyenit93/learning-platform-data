# Khóa lạc quan bằng trường version và xử lý xung đột trong MongoDB

## 1. Bài toán: hai người cùng sửa một document

Một ứng dụng quản lý hồ sơ sản phẩm lưu document MongoDB như sau:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  sku: "BOOK-001",
  name: "MongoDB căn bản",
  priceCents: 150000,
  description: "Sách nhập môn",
  version: 7,
  updatedAt: ISODate("2026-11-14T02:00:00Z")
}
```

Hai nhân viên cùng mở màn hình chỉnh sửa:

1. **Người A** đọc phiên bản `7`, đổi `priceCents` thành `160000`.
2. **Người B** cũng đọc phiên bản `7`, sửa `description`.
3. A lưu thành công.
4. B gửi toàn bộ bản sao document đã đọc lúc đầu, trong đó `priceCents` vẫn là `150000`.

Nếu ứng dụng cập nhật mà không kiểm tra bản ghi đã thay đổi hay chưa, lần ghi của B có thể **ghi đè giá mới của A bằng dữ liệu cũ**. Đây là hiện tượng *lost update* — mất cập nhật.

MongoDB bảo đảm một thao tác ghi trên **một document** có tính nguyên tử. Nhưng điều này **không tự bảo vệ logic đọc → xử lý trên ứng dụng → ghi lại** nếu nhiều request dùng các snapshot cũ. Ta cần một quy ước kiểm tra xem document đã thay đổi kể từ lúc đọc hay chưa.

**Optimistic concurrency control (OCC)** — thường gọi là *khóa lạc quan* — giải quyết bằng cách lưu một trường `version` và chỉ chấp nhận cập nhật nếu `version` trong database vẫn bằng phiên bản mà client đã đọc.

Sau bài này, bạn có thể:

- Phân biệt **tính nguyên tử của update một document** với **xung đột giữa hai luồng đọc–ghi**.
- Thiết kế trường `version` và thao tác **compare-and-set** (*CAS*).
- Viết `updateOne()` với filter chứa `_id` và `version`, dùng `$inc` để tăng phiên bản.
- Dùng `matchedCount` hoặc kết quả `findOneAndUpdate()` để nhận biết lần ghi có được chấp nhận không.
- Phân biệt document không tồn tại, version đã cũ, lỗi write concern và lỗi mạng không rõ kết quả.
- Chọn chính sách **409 Conflict**, **412 Precondition Failed**, đọc lại/merge hoặc retry có giới hạn.
- Tích hợp OCC với API, Node.js driver, validation, multi-document transaction và idempotency.

## 2. MongoDB nguyên tử ở mức nào?

### 2.1. Một update trên một document là nguyên tử

Ví dụ:

```javascript
db.products.updateOne(
  { _id: productId },
  {
    $set: {
      priceCents: 160000,
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
```

MongoDB áp dụng những thay đổi này với cùng một document như **một thao tác nguyên tử**. Reader không nhìn thấy trạng thái trung gian trong đó `priceCents` đã đổi nhưng `version` vẫn chưa tăng chỉ do một nửa lệnh trên được thực hiện.

Điều này giúp xây CAS, nhưng chưa đủ nếu filter chỉ có `_id`. Hai request dùng dữ liệu cũ vẫn có thể lần lượt cập nhật cùng document.

### 2.2. Vì sao `findOne()` rồi `updateOne()` có thể mất cập nhật?

Hãy xét mẫu code:

```javascript
const product = await products.findOne({ _id: productId });

// Người dùng chỉnh sửa sau khi client nhận dữ liệu...
const newPrice = computePriceFromOldData(product);

await products.updateOne(
  { _id: productId },
  { $set: { priceCents: newPrice } }
);
```

Trong lúc tính toán hoặc chờ người dùng, document có thể bị request khác sửa. Filter `{_id: productId}` vẫn khớp document, nên update không biết giá trị đã đọc trước đó đã lỗi thời.

### 2.3. Atomic không đồng nghĩa serial hóa toàn bộ nghiệp vụ

| Đặc tính | MongoDB bảo đảm hay không? |
| --- | --- |
| Một `updateOne` sửa nhiều field trong cùng document có tính nguyên tử | Có |
| Hai request có điều kiện ghi lên cùng document được kiểm tra điều kiện cập nhật tại lúc ghi | Có, trong ngữ nghĩa ghi của MongoDB |
| Một `findOne` và một `updateOne` độc lập được tự động xem là cùng một transaction | Không |
| Request ghi sau luôn phát hiện bản ghi nó đã đọc lúc trước bị sửa | Không, trừ khi có điều kiện/check thích hợp |
| Thao tác trên nhiều document tự nguyên tử chỉ vì cùng batch | Không |
| Version field tự tăng khi có bất kỳ writer nào sửa document | Không; ứng dụng phải thống nhất quy ước tăng version |

**Điểm quan trọng:** MongoDB không tự tạo OCC chỉ vì document có field `version`. Mọi đường ghi liên quan phải **tuân thủ giao thức**: kiểm version kỳ vọng và tăng version khi cập nhật cần bảo vệ.

## 3. Cơ chế compare-and-set với trường version

### 3.1. Đọc version rồi cập nhật có điều kiện

Giả sử client đã đọc:

```javascript
{
  _id: productId,
  name: "MongoDB căn bản",
  priceCents: 150000,
  version: 7
}
```

Request cập nhật truyền `expectedVersion = 7`. Server dùng lệnh:

```javascript
const expectedVersion = 7;

const result = db.products.updateOne(
  {
    _id: productId,
    version: expectedVersion
  },
  {
    $set: {
      priceCents: 160000,
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);

printjson(result);
```

Điều kiện:

```text
UPDATE chỉ thành công nếu:
    _id == productId
    VÀ
    version == expectedVersion
```

Về bản chất, server thực hiện một **conditional atomic update**: kiểm tra predicate ngay khi áp dụng ghi và tăng version cùng với dữ liệu trong một thao tác.

Nếu document vẫn ở `version = 7`, update được áp dụng và version thành `8`. Nếu document đã lên `8` do request khác, filter không khớp và **không có dữ liệu nào được sửa bởi lệnh này**.

### 3.2. Diễn biến hai request cạnh tranh

```text
Thời gian         Request A                     Request B
   |
   |          READ version=7                READ version=7
   |                 |                              |
   |                 v                              v
   |          chỉnh priceCents               chỉnh description
   |                 |                              |
   |                 v                              |
   |    UPDATE WHERE version=7                     |
   |    SET priceCents=160000                       |
   |    INC version +1                              |
   |                 |                              |
   |             matched=1                          |
   |             version=8                          |
   |                                                v
   |                                    UPDATE WHERE version=7
   |                                    SET description="..."
   |                                    INC version +1
   |                                                |
   v                                            matched=0

     A thành công; B phát hiện dữ liệu đã thay đổi.
```

Không cần application đặt một mutex toàn hệ thống cho mỗi product; MongoDB kiểm tra và áp dụng cập nhật có điều kiện trên document.

### 3.3. Cách đọc kết quả

`updateOne()` thường trả:

```javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0,
  upsertedId: null
}
```

Với một CAS **được xác nhận**:

- `matchedCount: 1`: một document khớp cả ID lẫn version, thao tác cập nhật đã được chấp nhận.
- `matchedCount: 0`: không có document nào khớp **toàn bộ filter**.
- `modifiedCount` có thể bằng `0` nếu một update thực sự không làm thay đổi giá trị; nhưng khi luôn `$inc` version thì một CAS thành công thường khiến document bị sửa.
- `upsertedCount` phải là `0` trong cập nhật OCC thông thường, vì không nên đặt `upsert: true`.

**Không được suy ra chỉ từ `matchedCount: 0` rằng document đã bị ai đó sửa.** Có thể document đã bị xóa, ID sai, tenant khác, version sai kiểu hoặc request không được phép truy cập theo filter.

### 3.4. Vì sao cần `$inc` version?

Nếu chỉ so version trong filter nhưng **không tăng version khi thành công**:

```javascript
// Sai về giao thức OCC:
db.products.updateOne(
  { _id: productId, version: 7 },
  { $set: { priceCents: 160000 } }
);
```

Sau lệnh, document vẫn ở version 7, nên request B với expectedVersion 7 có thể tiếp tục khớp và ghi đè. Điều kiện version trở nên vô nghĩa nếu không có quy ước thay đổi phiên bản.

Nguyên tắc: **mọi thao tác ghi được OCC bảo vệ phải thay đổi version trong cùng phép ghi nguyên tử**. Dùng `$inc: {version:1}` đơn giản hơn tự tính `version: oldVersion + 1` ở ứng dụng, vì database xử lý tăng số trong chính thao tác update.

## 4. Thực hành `mongosh`: mô phỏng hai người cùng chỉnh sửa

### 4.1. Chuẩn bị database riêng

Hãy kết nối MongoDB bằng `mongosh` tới môi trường thực hành bạn được phép sử dụng, ví dụ:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Trong shell:

```javascript
const lab = db.getSiblingDB("mongo_occ_row216_lab");
const products = lab.getCollection("products_demo");
const runId = "row216-" + new ObjectId().toHexString();
const productId = new ObjectId();

products.insertOne({
  _id: productId,
  runId,
  sku: "BOOK-216-01",
  name: "MongoDB căn bản",
  priceCents: NumberLong("150000"),
  description: "Sách nhập môn",
  status: "ACTIVE",
  version: NumberLong("1"),
  createdAt: new Date(),
  updatedAt: new Date()
});

print("database=" + lab.getName());
print("runId=" + runId);
printjson(products.findOne({ _id: productId, runId }));
```

`runId` là dấu phân biệt lượt thực hành, giúp dọn đúng document. `version` được lưu kiểu BSON Int64 bằng `NumberLong` để minh họa một lựa chọn kiểu số ổn định. Trong ứng dụng thực, cần thống nhất BSON numeric type giữa việc khởi tạo, so sánh và tăng phiên bản; JavaScript/driver còn có giới hạn biểu diễn số nguyên lớn, vì vậy không ép mù quáng những version quá lớn về JS `Number`.

### 4.2. Hai client cùng đọc một snapshot

Ta mô phỏng việc A và B nhận cùng dữ liệu:

```javascript
const snapshotA = products.findOne({ _id: productId, runId });
const snapshotB = products.findOne({ _id: productId, runId });

print("A.version=" + snapshotA.version);
print("B.version=" + snapshotB.version);
```

Cả hai sẽ nhìn thấy `version = 1` khi chưa có cập nhật xen vào.

### 4.3. A cập nhật thành công

```javascript
const resultA = products.updateOne(
  {
    _id: productId,
    runId,
    version: snapshotA.version
  },
  {
    $set: {
      priceCents: NumberLong("160000"),
      updatedAt: new Date()
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);

printjson(resultA);
printjson(products.findOne(
  { _id: productId, runId },
  { _id: 0, sku: 1, priceCents: 1, description: 1, version: 1 }
));
```

Sau bước này, version dự kiến là `2` và giá là `160000`. Kết quả `resultA.matchedCount` dự kiến bằng `1`.

### 4.4. B gửi thay đổi dựa trên version đã cũ

```javascript
const resultB = products.updateOne(
  {
    _id: productId,
    runId,
    version: snapshotB.version
  },
  {
    $set: {
      description: "Tài liệu thực hành MongoDB",
      updatedAt: new Date()
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);

printjson(resultB);
printjson(products.findOne(
  { _id: productId, runId },
  { _id: 0, priceCents: 1, description: 1, version: 1 }
));
```

Lệnh B dự kiến có `matchedCount: 0` vì version lưu đã là `2` trong khi snapshotB.version vẫn bằng `1`. Giá và mô tả không bị lệnh B thay đổi.

Khi xem output, điều quan trọng không phải MongoDB “từ chối B vì B đến sau”. MongoDB từ chối áp dụng cập nhật vì **filter của B không còn khớp**. Nếu B đã đọc version 2 trước khi gửi, kết quả có thể khác.

### 4.5. B đọc lại rồi đưa ra quyết định

Nếu nghiệp vụ cho phép chỉ cập nhật `description` mà không ảnh hưởng `priceCents`, B có thể tải lại document và phát sinh request mới:

```javascript
const latest = products.findOne({ _id: productId, runId });

const retryB = products.updateOne(
  {
    _id: productId,
    runId,
    version: latest.version
  },
  {
    $set: {
      description: "Tài liệu thực hành MongoDB",
      updatedAt: new Date()
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);

printjson(retryB);
printjson(products.findOne({
  _id: productId,
  runId
}));
```

Lần thử mới có thể thành công, làm version thành `3`, trong khi giá `160000` của A vẫn được giữ. Nhưng nếu một writer khác tiếp tục cập nhật giữa lần `findOne` và `updateOne`, retry vẫn có thể nhận `matchedCount:0`; **đọc lại không tạo ra khóa độc quyền**.

Việc tự động áp dụng lại thay đổi của B chỉ phù hợp vì ta **đã xác định** phép thay đổi `description` độc lập với giá. Với đơn hàng/thanh toán hoặc các field có quan hệ nghiệp vụ chặt, không tự retry bằng cách ghi đè bản mới mà không có bước kiểm tra xung đột chi tiết.

## 5. Xử lý `matchedCount: 0`: không tồn tại hay version xung đột?

### 5.1. Ba khả năng quan trọng

Khi thao tác:

```javascript
products.updateOne(
  { _id: productId, runId, version: expectedVersion },
  { $set: { name: "Tên mới" }, $inc: { version: NumberLong("1") } }
);
```

trả `matchedCount:0`, có thể:

1. Document đã bị **xóa** hoặc chưa từng tồn tại.
2. Document còn tồn tại nhưng **version khác**.
3. Filter còn có tenant, trạng thái hoặc điều kiện khác nên không khớp (ví dụ document đã chuyển trạng thái, quyền truy cập khác hoặc sai loại version).

Ứng dụng có thể tra cứu lại theo **ID và phạm vi quyền truy cập**:

```javascript
const currentValue = products.findOne({
  _id: productId,
  runId
});

if (!currentValue) {
  print("NOT_FOUND_OR_NOT_VISIBLE");
} else {
  print("VERSION_OR_PRECONDITION_CONFLICT");
  print("Current version: " + currentValue.version);
}
```

Tuy nhiên, lần đọc thứ hai cũng có thể chịu cạnh tranh. Đây là **ảnh chụp tình trạng tại thời điểm đối soát**, không phải bằng chứng rằng document chắc chắn đã hoặc chưa tồn tại ở đúng thời điểm lệnh update thất bại.

### 5.2. Không tiết lộ tồn tại của tài nguyên người khác

Trong ứng dụng đa tenant, filter update có thể là:

```javascript
{
  _id: productId,
  tenantId: authenticatedTenantId,
  version: expectedVersion
}
```

Nếu trả `0`, server chỉ nên đọc lại bằng điều kiện có **tenant đã xác thực**. Không truy vấn lại chỉ theo `_id` rồi thông báo “document tồn tại nhưng bạn không có quyền” nếu chính sách bảo mật yêu cầu che giấu sự tồn tại của tài nguyên.

OCC và authorization giải quyết hai bài toán khác nhau; filter phải thể hiện cả hai.

### 5.3. Mapping lỗi ở tầng API

Một API REST có thể quy định:

| Tình huống | Phản hồi thường gặp |
| --- | --- |
| CAS thành công | `200 OK` với document mới hoặc `204 No Content` |
| Document không tồn tại trong phạm vi truy cập | `404 Not Found` |
| Version đã cũ theo API dùng trường version riêng | `409 Conflict` |
| Header điều kiện `If-Match` không thỏa | `412 Precondition Failed` |
| Client bắt buộc phải gửi precondition nhưng không gửi | `428 Precondition Required` nếu contract yêu cầu |
| Dữ liệu đầu vào không hợp lệ | `400 Bad Request` hoặc `422 Unprocessable Content` theo quy ước API |
| Lỗi ghi tạm thời | Phản hồi hệ thống phù hợp; retry an toàn theo chính sách |

HTTP status chỉ là **giao diện**; ràng buộc đúng đắn nằm ở thao tác cập nhật có điều kiện tại MongoDB. Một API không nên báo thành công trước khi có mức xác nhận ghi phù hợp.

## 6. Thiết kế trường version

### 6.1. Tạo version từ khi insert

Document mới nên có version khởi tạo rõ ràng:

```javascript
db.products.insertOne({
  sku: "BOOK-002",
  name: "MongoDB chuyên sâu",
  priceCents: NumberLong("200000"),
  version: NumberLong("1"),
  createdAt: new Date(),
  updatedAt: new Date()
});
```

Có thể chọn khởi tạo `0` hoặc `1`; điều quan trọng là **nhất quán toàn hệ thống**. Nếu dữ liệu cũ không có `version`, phải có migration/compatibility policy trước khi yêu cầu tất cả writer dùng OCC.

### 6.2. Kiểu dữ liệu và quy tắc tăng

Version thường là **số nguyên đơn điệu tăng**. Những lựa chọn thường gặp:

- BSON `Int32` nếu miền giá trị đủ cho vòng đời document.
- BSON `Int64` nếu muốn dư địa lớn hơn và driver xử lý được kiểu `Long` phù hợp.
- Một số hệ thống dùng token opaque hoặc UUID thay cho số, nhưng lúc đó lệnh cập nhật và cách sinh token phải được thiết kế khác.

Nếu dùng `Long` trong Node.js driver, tránh chuyển một số nguyên 64-bit rất lớn thành JS `Number` rồi so sánh không chính xác. Không dùng timestamp do client tạo như “version” nếu mục tiêu là kiểm tra chính xác mọi lần ghi: hai writer có thể có cùng timestamp, đồng hồ có thể lệch và độ phân giải có thể không đủ.

### 6.3. Mọi writer phải tuân thủ giao thức

Giả sử một service dùng CAS và tăng version, nhưng worker khác vẫn viết:

```javascript
// Writer phá giao thức OCC nếu thao tác sửa business data
// nhưng không kiểm/không tăng version.
db.products.updateOne(
  { _id: productId },
  { $set: { priceCents: 99999 } }
);
```

Document thay đổi mà version không tăng. Client đang giữ expectedVersion cũ vẫn có thể cập nhật thành công và ghi đè giá mới. Vì vậy OCC chỉ đáng tin khi:

- Các API chỉnh sửa document đều dùng filter version và tăng version.
- Các worker/import/maintenance script có cùng chính sách hoặc được quản lý với đường thay đổi có kiểm soát.
- Migration sửa dữ liệu nghiệp vụ có thể cần bump version.
- Schema validation, quan sát và kiểm tra triển khai ngăn dữ liệu thiếu/sai kiểu version theo chính sách.

### 6.4. Có cần index riêng trên version?

Nếu CAS lọc bằng:

```javascript
{ _id: productId, version: expectedVersion }
```

MongoDB thường dùng index mặc định trên `_id` để tìm tối đa một document rồi kiểm thêm version. **Không nhất thiết cần index `{version:1}`** chỉ để thực hiện CAS theo `_id`.

Trong hệ thống đa tenant, query có thể cần thêm `tenantId`/shard key phục vụ routing; index cụ thể phụ thuộc topology và filter. Nếu CAS dựa vào `{tenantId, sku}` thay vì `_id`, nên có unique index theo **khóa nghiệp vụ ổn định**. `version` không thay unique index để chống chèn hai document giống nhau.

### 6.5. Không cho client tự quyết version mới

Request có thể gửi:

```javascript
{
  expectedVersion: 7,
  patch: {
    priceCents: 160000
  }
}
```

Server phải xác minh `expectedVersion` hợp lệ, nhưng không cho client tự gửi `version: 9999` để ghi vào database. Hãy tách `expectedVersion` (điều kiện) khỏi `nextVersion` (được server tăng nguyên tử).

Tránh cho payload cập nhật chứa `version`, `_id` hoặc những field hệ thống khác mà chưa được whitelist; nếu dùng `$set` trực tiếp từ body không kiểm soát, client có thể phá protocol OCC hoặc thay field không được phép.

## 7. Node.js driver: viết hàm cập nhật có kiểm soát xung đột

### 7.1. Hàm update có điều kiện

Ví dụ dùng MongoDB Node.js driver. Giả định:

- `products` là collection từ một `MongoClient` đã kết nối.
- `productId` là `ObjectId` hợp lệ và document đã có field `version`.
- `tenantId` lấy từ ngữ cảnh đã xác thực.
- `expectedVersion` được chuyển sang đúng kiểu BSON theo schema của ứng dụng.
- `patch` chỉ chứa các field đã được kiểm tra.

```javascript
import { Long } from "mongodb";

async function updateProduct(products, {
  productId,
  tenantId,
  expectedVersion,
  patch
}) {
  // Minh họa expectedVersion đã được validate là số nguyên
  // an toàn trước khi chuyển thành BSON Long.
  const expected = Long.fromNumber(expectedVersion);

  const filter = {
    _id: productId,
    tenantId,
    version: expected
  };

  const update = {
    $set: {
      ...patch,
      updatedAt: new Date()
    },
    $inc: {
      version: Long.ONE
    }
  };

  const result = await products.updateOne(
    filter,
    update,
    { upsert: false }
  );

  if (result.matchedCount === 1) {
    return {
      outcome: "UPDATED",
      previousVersion: expectedVersion
    };
  }

  // Chỉ đọc trong đúng tenant đã xác thực.
  const current = await products.findOne(
    { _id: productId, tenantId },
    { projection: { version: 1, updatedAt: 1 } }
  );

  if (!current) {
    return { outcome: "NOT_FOUND" };
  }

  return {
    outcome: "CONFLICT",
    currentVersion: current.version
  };
}
```

Đây là **hàm minh họa CAS**, không phải API production hoàn chỉnh. Tầng gọi phải kiểm tra danh sách field cho phép, kiểu giá trị, authorization, write concern, các lỗi tài nguyên và cách serialize `Long` ra JSON. `Long.fromNumber()` chỉ nên dùng khi input đã nằm trong khoảng **số nguyên an toàn của JavaScript**; với version rất lớn cần định dạng chuỗi và parse chính xác theo driver.

### 7.2. Không dùng body tùy ý làm `$set`

Một lỗi phổ biến:

```javascript
// Không an toàn:
await products.updateOne(
  { _id: productId, version: expected },
  {
    $set: request.body,
    $inc: { version: Long.ONE }
  }
);
```

Client có thể gửi cả `version`, `_id` hoặc đường dẫn field không được phép. Ngay cả khi server từ chối xung đột operator trên version, đây vẫn là lỗi contract và có thể làm hỏng tính đúng đắn của những field khác.

Thay vào đó, server xây bản update từ danh sách thuộc tính được phép:

```javascript
const patch = {};

if (typeof body.name === "string") {
  patch.name = body.name;
}

if (Number.isSafeInteger(body.priceCents) && body.priceCents >= 0) {
  patch.priceCents = Long.fromNumber(body.priceCents);
}

// Các field bắt buộc, quyền sửa và giới hạn được validate riêng.
```

Trong hệ thống thật, dữ liệu sai phải báo lỗi rõ thay vì **âm thầm bỏ qua** field không hợp lệ. Đoạn code trên chỉ minh họa việc tạo một object update từ field được kiểm soát.

### 7.3. Nhận lại document mới bằng `findOneAndUpdate`

`findOneAndUpdate` kết hợp tìm và cập nhật theo điều kiện trong một thao tác, có thể trả document sau update:

```javascript
const updated = await products.findOneAndUpdate(
  {
    _id: productId,
    tenantId,
    version: expected
  },
  {
    $set: { name: "Tên mới", updatedAt: new Date() },
    $inc: { version: Long.ONE }
  },
  {
    returnDocument: "after",
    upsert: false,
    includeResultMetadata: false
  }
);

if (updated === null) {
  // Không khớp: not found hoặc OCC conflict.
}
```

Trong các phiên bản Node.js driver khác nhau, `findOneAndUpdate` có thay đổi về giá trị trả về và tùy chọn metadata. Hãy đọc API của **phiên bản driver đang dùng** thay vì giả định luôn trả một object bọc `value`.

Khi không có document khớp, `null` là kết quả hợp lý với chế độ trả trực tiếp document. Tương tự `matchedCount:0`, cần đọc lại (nếu muốn) để phân loại not found và conflict.

### 7.4. Chọn `updateOne` hay `findOneAndUpdate`?

| Nhu cầu | Hướng thường phù hợp |
| --- | --- |
| Chỉ cần biết CAS thành công hay thất bại | `updateOne` + `matchedCount` |
| Cần document sau update từ cùng thao tác | `findOneAndUpdate` + `returnDocument:"after"` |
| Cần tra cứu bản mới sau khi updateOne | Có thể đọc tiếp, nhưng reader có thể thấy các thay đổi đồng thời tiếp theo |
| Muốn chỉ update nếu trạng thái cũ thỏa điều kiện | Đưa state predicate vào filter, **không upsert** |
| Muốn xử lý nhiều document nhất quán | Xem xét transaction; OCC một document chưa đủ |

Đừng tự đánh giá chỉ dựa trên số round-trip. `findOneAndUpdate` có đặc điểm hiệu năng và hành vi khác `updateOne` tùy topology/driver; hãy chọn theo nhu cầu kết quả và khối lượng thực tế.

## 8. Hòa giải xung đột: từ phát hiện đến quyết định nghiệp vụ

### 8.1. Không nên retry mù quáng

Một cách xử lý sai:

```javascript
// Ý tưởng SAI khi dùng bản sao cũ:
while (!updated) {
  await products.updateOne(
    { _id: productId },
    { $set: staleDocument }
  );
}
```

Việc bỏ version khỏi filter chỉ để “cập nhật cho bằng được” vô hiệu hóa OCC. Nếu retry với version mới nhưng **giữ nguyên toàn bộ snapshot cũ**, lần retry cũng có thể ghi đè thay đổi đã được người khác thực hiện.

### 8.2. Ba chính sách xử lý thông dụng

| Chính sách | Cách làm | Khi phù hợp |
| --- | --- | --- |
| **Báo conflict cho người dùng** | Trả version hiện tại và yêu cầu người dùng tải lại/so sánh | Form chỉnh sửa hồ sơ, nội dung quan trọng, thay đổi khó tự hợp nhất |
| **Đọc mới và áp lại một phép thay đổi có thể hòa giải** | Đọc document mới, kiểm invariant, xây patch mới, CAS theo version mới | Phép thay đổi độc lập và được định nghĩa rõ, ví dụ cập nhật một trường không phụ thuộc trường khác |
| **Merge có quy tắc nghiệp vụ** | So base/client/current, phát hiện field nào xung đột, trình người dùng hoặc rule chọn | Tài liệu nhiều trường, workflow cộng tác hoặc editor |

Chính sách “last write wins” có thể có trong một số hệ thống nhưng đó là **quyết định nghiệp vụ bỏ qua một số xung đột**, không phải mặc định an toàn khi dùng OCC.

### 8.3. Phân biệt cập nhật độc lập và cập nhật phụ thuộc

Giả sử:

- A đổi `priceCents` từ `150000` thành `160000`.
- B đổi `description`.

Nếu giao diện chỉ gửi **patch của field đã đổi**, và nghiệp vụ cho phép hai trường độc lập, B có thể đọc version mới rồi áp patch description mà không đè lại giá.

Nhưng xét:

- A đổi `discountPercent` từ `10` lên `20`.
- B tính `finalPriceCents` từ giá và discount cũ, sau đó muốn ghi giá cuối.

Ở đây bản cập nhật của B **phụ thuộc snapshot cũ**. Không thể an toàn chỉ lấy version mới rồi giữ kết quả tính toán cũ. Phải **tính lại dựa trên document mới nhất** và kiểm tra invariant giá.

### 8.4. Three-way merge

Khi người dùng chỉnh nhiều field, có thể so sánh ba bản:

1. **Base**: document client đọc ban đầu.
2. **Client**: bản người dùng muốn lưu.
3. **Current**: document mới nhất trên server sau khi CAS thất bại.

Ý tưởng:

```text
base.name        = "Sách cũ"
client.name      = "Sách mới"
current.name     = "Sách cũ"

=> Client sửa name, server chưa sửa name:
   Có thể áp client.name.

base.price       = 150000
client.price     = 155000
current.price    = 160000

=> Cả client và server cùng sửa price:
   CONFLICT, cần quyết định.
```

Một thuật toán merge có thể chỉ tự ghép những field **không chồng lấn**. Khi có quan hệ giữa các field, kiểm tra chồng lấn là chưa đủ: thay đổi số lượng, giá, hạn mức hoặc trạng thái cần áp quy tắc nghiệp vụ riêng.

### 8.5. Retry có giới hạn và backoff

Nếu chính sách cho phép retry tự động:

- Mỗi lần lấy lại document theo đúng ID và tenant.
- **Tính lại** thay đổi từ trạng thái mới nhất, không gửi lại nguyên bản sao cũ.
- Dùng expectedVersion mới trong filter.
- Giới hạn số lần thử, ví dụ vài lần, theo tải và SLA.
- Thêm backoff và jitter nếu có nhiều writer tranh một document.
- Nếu xung đột liên tục, trả conflict hoặc chuyển sang một quy trình khác, thay vì vòng lặp vô hạn.

Retry có thể làm thay đổi thứ tự nghiệp vụ; cần cân nhắc khi cập nhật các trường phụ thuộc thời gian hoặc quy tắc ưu tiên request.

## 9. Mẫu retry có điều kiện trong Node.js

Giả sử hành động nghiệp vụ là **đặt mô tả** bằng một giá trị mới, và sản phẩm cho phép áp lại thay đổi đó khi một field khác đã đổi. Mã minh họa:

```javascript
import { Long } from "mongodb";

async function setDescriptionWithLimitedRetry(
  products,
  { productId, tenantId, newDescription },
  maxAttempts = 3
) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const current = await products.findOne({
      _id: productId,
      tenantId
    });

    if (!current) {
      return { outcome: "NOT_FOUND" };
    }

    // Quyết định tại đây: chỉ cho phép cập nhật khi ACTIVE.
    if (current.status !== "ACTIVE") {
      return { outcome: "INVALID_STATE" };
    }

    const result = await products.updateOne(
      {
        _id: productId,
        tenantId,
        version: current.version,
        status: "ACTIVE"
      },
      {
        $set: {
          description: newDescription,
          updatedAt: new Date()
        },
        $inc: { version: Long.ONE }
      },
      { upsert: false }
    );

    if (result.matchedCount === 1) {
      return { outcome: "UPDATED", attempt };
    }

    // Đã thay đổi giữa lần đọc và ghi; thử lại có giới hạn.
    // Trong production, thêm backoff/jitter phù hợp.
  }

  return { outcome: "TOO_MUCH_CONTENTION" };
}
```

**Giới hạn của ví dụ:** hàm cố ý định nghĩa chính sách “mô tả có thể được đặt lại trên document ACTIVE” — không phù hợp nếu hai người đang cùng biên tập `description` và muốn phát hiện đè nhau. Trong editor cộng tác, thay vì tự retry, có thể yêu cầu người dùng xử lý conflict khi chính **trường họ sửa** đã bị thay đổi.

Đoạn code trên xử lý kết quả CAS thông thường, **không tự retry mọi lỗi network/write concern**. Với lỗi không rõ kết quả ghi, cần idempotency và đối soát riêng như phần sau.

## 10. Version-based OCC và HTTP ETag/If-Match

### 10.1. Truyền version từ API đến database

Một API có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-7"

{
  "id": "...",
  "name": "MongoDB căn bản",
  "priceCents": 150000,
  "version": 7
}
```

Client chỉnh dữ liệu rồi gửi:

```http
PATCH /products/123 HTTP/1.1
Content-Type: application/json
If-Match: "product-7"

{
  "priceCents": 160000
}
```

Server giải mã precondition, đối chiếu version tương ứng với document, rồi thực hiện CAS:

```javascript
db.products.updateOne(
  {
    _id: productId,
    tenantId: authenticatedTenantId,
    version: NumberLong("7")
  },
  {
    $set: { priceCents: NumberLong("160000") },
    $inc: { version: NumberLong("1") }
  }
);
```

Nếu không khớp, API có thể trả `412 Precondition Failed` theo semantics `If-Match`. Nếu API dùng trường `expectedVersion` trong JSON body thay vì header, `409 Conflict` là một lựa chọn phổ biến. Quan trọng là contract thống nhất để client biết khi nào cần tải lại.

### 10.2. ETag không phải luôn chỉ là chuỗi version

ETag trong HTTP là **validator của representation**. Nếu response khác nhau theo ngôn ngữ, quyền hiển thị hoặc cách serialize, một ETag đúng theo semantics HTTP phải được thiết kế phù hợp với representation đó. Dùng chuỗi `"product-7"` ở ví dụ chỉ minh họa cách biểu diễn validator trong một API có contract rõ ràng.

ETag dạng weak (có tiền tố `W/`) không phù hợp cho điều kiện strong comparison của `If-Match`. Nếu triển khai HTTP conditional requests, cần đọc và áp dụng đúng semantics của giao thức, không chỉ xử lý một chuỗi tùy ý.

### 10.3. Giao diện cho người dùng khi conflict

Thay vì thông báo chung “Lưu thất bại”, một ứng dụng có thể:

1. Nói rõ hồ sơ đã thay đổi trên server.
2. Tải phiên bản mới và hiển thị các trường khác biệt.
3. Cho người dùng chọn giữ thay đổi của họ, giữ dữ liệu mới hoặc điều chỉnh.
4. Gửi request mới với version hiện tại sau khi người dùng xác nhận.

Không nên trả toàn bộ document chứa dữ liệu nhạy cảm trong lỗi conflict nếu user không có quyền đọc những field đó.

## 11. Kết hợp version với điều kiện nghiệp vụ

### 11.1. Kiểm tra trạng thái trước khi chuyển

Giả sử một đơn hàng chỉ được chuyển từ `PENDING` sang `APPROVED`:

```javascript
const result = db.orders.updateOne(
  {
    _id: orderId,
    tenantId: authenticatedTenantId,
    version: expectedVersion,
    status: "PENDING"
  },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
```

Filter kết hợp ba loại điều kiện:

- **Identity/authorization**: `_id` và `tenantId`.
- **OCC**: `version` bằng phiên bản được đọc.
- **Business invariant**: `status` vẫn là `PENDING`.

Nếu `matchedCount: 0`, nguyên nhân có thể là version thay đổi, status không còn PENDING hoặc document không thuộc phạm vi. Đọc lại có điều kiện và phân loại theo contract.

**Không bật `upsert: true`** trong kiểu cập nhật chuyển trạng thái này. Khi document hiện có không khớp do version/status, upsert có thể thử **tạo document mới**, dẫn đến duplicate key hoặc tạo bản ghi ngoài ý muốn nếu thiếu unique constraint phù hợp.

### 11.2. Trừ tồn kho: có thể dùng điều kiện trực tiếp

Giả sử thao tác chỉ cần trừ 2 sản phẩm nếu tồn kho đủ:

```javascript
db.inventory.updateOne(
  {
    _id: skuId,
    quantity: { $gte: 2 }
  },
  {
    $inc: {
      quantity: -2,
      version: 1
    }
  }
);
```

Đây là update **nguyên tử trên một document**, nên điều kiện `quantity >= 2` được kiểm tại thời điểm ghi và không trừ quá số lượng có sẵn do hai writer cùng đọc số tồn cũ.

Trong trường hợp này, **không cần version để bảo vệ phép trừ đơn giản**, vì `$inc` và predicate quantity đã thể hiện trực tiếp bất biến. Version vẫn có thể hữu ích cho các thay đổi khác hoặc để theo dõi trạng thái.

Ngược lại, nếu ứng dụng đọc tồn kho cũ, tính `newQuantity = oldQuantity - 2` trên client rồi `$set` `quantity` mà không điều kiện, các writer có thể ghi đè kết quả của nhau.

### 11.3. OCC không đồng nghĩa idempotency

Nếu request trừ tồn kho bị gửi lại sau khi đã thành công, phiên bản mới có thể khiến request retry với expectedVersion cũ **không khớp**. Điều này giúp phát hiện không nên áp lại một snapshot cũ, nhưng không tự cho biết **request nào** đã gây thay đổi.

Nếu sau timeout client đọc version mới rồi tiếp tục trừ 2 lần nữa, số lượng vẫn bị trừ hai lần. Với thao tác quan trọng phải xử lý **một lần cho mỗi mã giao dịch**, cần lưu operation ID/idempotency key ổn định và cơ chế chống xử lý lặp.

## 12. Khi lỗi mạng xảy ra: CAS thành công hay chưa?

### 12.1. Timeout có thể khiến kết quả chưa xác định

Luồng:

```text
Client                          MongoDB
   |                               |
   |--- UPDATE version=7 --------> |
   |                               |  Ghi thành công, version=8
   |        (response lost)        |
   | <---- timeout --------------- X
   |
   v
Client không biết update đã commit theo mức mong muốn hay chưa.
```

Nếu client lập tức gửi **một operation mới** với `expectedVersion:7`, MongoDB có thể trả `matchedCount:0`. Không thể kết luận lần đầu thất bại; có thể **chính lần đầu đã tăng version**.

Đây là khác biệt giữa:

- **Concurrency conflict**: biết document hiện tại không còn khớp version kỳ vọng.
- **Unknown write outcome**: không biết lần ghi ban đầu đã có hiệu lực/đạt write concern cần thiết chưa.

### 12.2. Driver retryable writes không thay thế idempotency

MongoDB driver có khả năng retry một số loại ghi với retryable writes trong các điều kiện topology và cấu hình phù hợp. Nhưng API gateway, mobile client hoặc message queue có thể phát lại **một request nghiệp vụ mới**, không phải chỉ retry nội bộ cùng một lệnh driver.

Một thao tác gửi lại có thể được diễn giải thành hành động mới nếu thiếu `operationId` ổn định. Do đó không được coi việc bật retryable writes là toàn bộ giải pháp chống lặp giao dịch.

### 12.3. Đối soát bằng operation ID

Một thiết kế cho nghiệp vụ quan trọng:

```javascript
{
  _id: orderId,
  version: NumberLong("12"),
  status: "APPROVED",
  lastOperationId: "approve-order-op-82f1"
}
```

Một cách đơn giản là ghi `lastOperationId` trong cùng update CAS để biết thao tác vừa thực hiện. Nhưng chỉ **một trường lastOperationId** không đủ làm sổ theo dõi khi nhiều operation tiếp theo đã thay thế nó.

Với yêu cầu chống xử lý lặp lâu dài, cần lưu một bản ghi operation hoặc idempotency registry có unique key và trạng thái, phối hợp với cập nhật nghiệp vụ bằng một transaction hoặc một mô hình một document nguyên tử được thiết kế phù hợp. Khi có side effect ngoài MongoDB, cân nhắc transactional outbox hoặc idempotent consumer.

### 12.4. Write concern và mức xác nhận

Ứng dụng có thể yêu cầu write concern như `w: "majority"` để tăng mức xác nhận độ bền. Khi nhận `writeConcernError` hoặc timeout, không được tự suy ra “không ghi gì”: thao tác có thể đã áp dụng ở primary nhưng chưa đạt xác nhận mong muốn.

Đọc lại document có thể giúp quan sát dữ liệu, nhưng **nhìn thấy version mới trên một node không tự chứng minh lần ghi đã đạt majority acknowledgment**. Chính sách xử lý phải phù hợp read concern, write concern, topology và yêu cầu nghiệp vụ.

## 13. Khóa lạc quan và transaction đa document

### 13.1. Khi OCC một document là đủ

Thường phù hợp cho:

- Chỉnh sửa hồ sơ khách hàng trong một document.
- Cập nhật cấu hình người dùng.
- Chỉnh một catalog item với quy tắc field rõ ràng.
- Chuyển trạng thái của một document.
- Quản lý một aggregate nghiệp vụ được mô hình hóa gọn trong một document.

Khi toàn bộ invariant nằm trong **một document**, phép ghi có điều kiện nguyên tử có thể là giải pháp đơn giản và hiệu quả.

### 13.2. Khi cần multi-document transaction

Ví dụ duyệt đơn hàng đòi hỏi:

1. Cập nhật trạng thái order.
2. Giảm tồn kho ở document inventory khác.
3. Ghi một outbox event trong collection khác.

OCC trên order **không tự làm ba thao tác cùng commit hoặc rollback**. Cần xem xét transaction đa document nếu nghiệp vụ đòi nhất quán nguyên tử.

Với transaction, hai writer có thể gặp **write conflict** ở tầng database và driver có thể retry theo chính sách. Điều này khác với **OCC conflict** do ứng dụng cố ý đưa version vào filter và nhận `matchedCount:0`.

| Vấn đề | OCC bằng version | Transaction đa document |
| --- | --- | --- |
| Phát hiện stale update một document | Có, nếu mọi writer theo giao thức | Có thể giúp cô lập thay đổi, nhưng semantics khác CAS |
| Cập nhật nhiều field trong một document nguyên tử | MongoDB đã hỗ trợ | Không cần transaction riêng chỉ vì nhiều field |
| Nhiều document cùng thành công hoặc cùng rollback | Không tự bảo đảm | Có |
| Bảo vệ business key unique | Không | Không; vẫn cần unique index |
| Ngăn client phát lại side effect | Không tự bảo đảm | Không tự bảo đảm |
| Xung đột khi nhiều writer cạnh tranh | CAS trả không khớp | Có thể có write conflict/transient transaction error |

Transaction có chi phí và giới hạn riêng; không nên dùng transaction đa document chỉ để thay một `updateOne` CAS nếu không có invariant liên document.

### 13.3. Retry transaction không phải retry business operation tùy tiện

Khi dùng `session.withTransaction(...)`, driver có thể chạy lại callback khi gặp một số lỗi tạm thời. Không đặt thao tác gửi email, gọi thanh toán hoặc phát thông báo ra hệ ngoài trong callback nếu nó không idempotent: callback có thể chạy nhiều lần dù transaction cuối cùng chỉ commit một lần.

Thao tác nghiệp vụ cần khóa idempotency; phần giao tiếp bên ngoài cần outbox/inbox hoặc cơ chế bảo vệ riêng.

## 14. OCC khi có nhiều document con và mảng

### 14.1. Thay đổi một phần tử mảng vẫn thay version của document

Giả sử document:

```javascript
{
  _id: projectId,
  version: 5,
  tasks: [
    { taskId: "T1", title: "Thiết kế", done: false },
    { taskId: "T2", title: "Kiểm thử", done: false }
  ]
}
```

Muốn đánh dấu T1 hoàn tất:

```javascript
db.projects.updateOne(
  {
    _id: projectId,
    version: 5,
    "tasks.taskId": "T1"
  },
  {
    $set: { "tasks.$.done": true },
    $inc: { version: 1 }
  }
);
```

Nếu version đã đổi do một writer khác sửa T2, thao tác T1 sẽ conflict dù **hai task khác nhau**. Đây là tính chất **document-level OCC**: version đại diện cho một phiên bản của cả document.

### 14.2. Conflict giả khi hai trường độc lập

Một document chứa hàng nghìn phần tử con có thể chịu nhiều update song song. Nếu mọi thao tác đều tăng cùng một `version`, tần suất conflict có thể cao.

Cân nhắc:

- Cho phép patch độc lập mà không cần version toàn document **chỉ khi** invariant cho phép.
- Tách các phần tử thành document riêng để giảm cạnh tranh.
- Quản lý version ở mức phần tử/aggregate con với cơ chế cập nhật đúng đường dẫn và ngữ nghĩa.
- Dùng phép toán nguyên tử `$inc`, `$addToSet` hoặc update có điều kiện khi có thể thay read-modify-write.

Không tách document chỉ để giảm conflict nếu việc tách làm mất tính nguyên tử của những bất biến phải được quản lý cùng nhau. Đây là đánh đổi giữa **độ hạt của tính nguyên tử** và **tần suất cạnh tranh**.

### 14.3. Chọn ranh giới aggregate nghiệp vụ

Nếu đơn hàng và mọi line item được lưu trong một document, version của order có thể bảo vệ việc sửa tất cả line item cùng nhau. Nếu line item nằm ở collection khác, version của order không tự phát hiện mọi thay đổi của từng line item trừ khi hệ thống có quy tắc cập nhật/transaction đồng bộ.

Mô hình document, chọn invariant và giao thức concurrency cần được thiết kế như **một tổng thể**.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đọc document rồi `$set` theo ID, không kiểm version | Lost update khi hai request dùng snapshot cũ | CAS với filter version |
| Có field version nhưng quên `$inc` khi update | Writer sau vẫn khớp version cũ | Tăng version trong cùng thao tác nguyên tử |
| Một writer cập nhật data mà không tăng version | Giao thức OCC bị phá | Thống nhất mọi đường ghi |
| Khi `matchedCount:0` luôn trả “đã bị người khác sửa” | Có thể thực ra not found/sai tenant/state | Đối soát theo ID và phạm vi quyền |
| Bật `upsert:true` cho CAS | Có thể cố insert khi version đã cũ | CAS dùng update **không upsert** |
| Khi conflict tự động ghi đè toàn snapshot cũ | Đánh mất thay đổi của người khác | Rebase patch có quy tắc hoặc báo conflict |
| Retry vô hạn khi document bị tranh chấp | Tăng tải, latency và nguy cơ vòng lặp | Giới hạn số lần, backoff/jitter |
| Lấy version từ timestamp client | Đồng hồ lệch, trùng timestamp, thiếu độ chính xác | Số nguyên/token theo giao thức được kiểm soát |
| Client được sửa version trong payload | Có thể phá concurrency protocol | Whitelist field, server tự tăng |
| Tạo index `{version:1}` cho mọi CAS theo `_id` | Tốn index không cần thiết | Đánh giá index `_id`/business key và workload |
| Đồng nhất `matchedCount:0` với lỗi MongoDB write conflict | Nhầm xung đột nghiệp vụ và lỗi database | Phân biệt kết quả CAS với error/label |
| Coi timeout là chắc chắn chưa ghi | Retry có thể lặp tác dụng | Đối soát, idempotency key, write concern phù hợp |
| Cho rằng version chống trừ tiền lặp | Một request mới có thể đọc version mới và trừ thêm | Operation ID, unique registry/transaction |
| Dùng OCC của order để bảo vệ nhiều collection | Mất tính nguyên tử liên document | Transaction hoặc thiết kế aggregate thích hợp |
| Tự retry chỉnh sửa field có xung đột | Ghi đè ý định người dùng | Three-way merge hoặc yêu cầu xác nhận |
| Bọc side effect bên ngoài vào transaction callback | Callback retry có thể gọi side effect nhiều lần | Outbox/idempotent consumer |
| Không xử lý document legacy thiếu version | CAS không khớp hoặc reset không nhất quán | Migration và validation trước rollout |

## 16. Triển khai OCC theo từng giai đoạn

### 16.1. Bước 1: định nghĩa invariant và phạm vi version

Hỏi rõ:

- Version đại diện cho **một document**, một phần tử con hay một aggregate nghiệp vụ?
- Thay đổi nào buộc tăng version?
- Các thao tác ghi độc lập có được phép tự merge không?
- Thao tác nào bắt buộc trả conflict để người dùng xác nhận?
- Điều kiện business/tenant nào phải đồng thời xuất hiện trong CAS?

Nếu không có quy tắc rõ, các service có thể diễn giải version khác nhau và mất tác dụng chống lost update.

### 16.2. Bước 2: khởi tạo và migration

Đảm bảo document mới có version chuẩn. Với document cũ:

1. Kiểm tra các kiểu `version` hiện có và phần tử thiếu field.
2. Chọn chính sách migration, ví dụ gán version khởi tạo phù hợp khi không có.
3. Phối hợp thời điểm rollout giữa các writer cũ và mới.
4. Bổ sung schema validation nếu cần yêu cầu version có mặt và đúng loại BSON.
5. Giám sát xung đột trong giai đoạn chuyển đổi.

Không gắn cùng một version cố định cho document cũ và chạy đồng thời writer không tuân thủ giao thức rồi mặc định OCC đã bảo vệ hoàn toàn.

### 16.3. Bước 3: API trả version và bắt buộc precondition

Đầu ra GET cần có version hoặc ETag theo contract. Update API nhận expectedVersion/If-Match và **bắt buộc gửi** cho những thao tác cần OCC. Không tự dùng version mới nhất thay cho client khi request thiếu precondition, vì như vậy lại cho phép ghi đè không phát hiện.

### 16.4. Bước 4: cập nhật bằng CAS

Sử dụng:

```javascript
{
  filter: {
    _id: targetId,
    tenantId: authenticatedTenantId,
    version: expectedVersion
  },
  update: {
    $set: allowedChanges,
    $inc: { version: 1 }
  },
  options: { upsert: false }
}
```

Đây là **mẫu cấu trúc mô tả**, không phải lệnh MongoDB trực tiếp. Trong driver, truyền ba thành phần vào `updateOne(filter, update, options)` và kiểm tra kết quả đã được xác nhận.

### 16.5. Bước 5: quan sát và xử lý conflict

Log có thể chứa:

- request ID hoặc correlation ID;
- ID document/tenant theo chính sách bảo mật;
- expectedVersion;
- outcome `UPDATED / CONFLICT / NOT_FOUND / UNKNOWN`;
- số lần retry và thời gian xử lý;
- mã lỗi MongoDB khi có lỗi thực sự.

Không log toàn bộ payload nhạy cảm hoặc thông tin xác thực chỉ để debug version. Theo dõi **conflict rate**, độ trễ update và số lần thử trung bình để phát hiện document “hot”.

### 16.6. Bước 6: kiểm tra các đường ghi đặc biệt

Những đường dễ bị bỏ sót:

- script nhập dữ liệu;
- bulk write hoặc batch job;
- event consumer;
- cập nhật bằng aggregation pipeline;
- admin tool;
- migration;
- thao tác replace document;
- ứng dụng cũ chưa cập nhật API.

Với mỗi đường, xác định rõ liệu nó cần CAS, cần bump version hoặc là ngoại lệ được quản lý. Nếu không, một writer không tuân thủ có thể phá bảo đảm của toàn bộ hệ thống.

## 17. Tự kiểm tra bằng các tình huống thực tế

### 17.1. Tình huống A: hai người cùng sửa giá

Document có `version:10`. A và B đều đọc version 10. A đặt giá 100000, B đặt giá 120000. Cả hai dùng filter `{_id,version:10}` và `$inc` version.

Hỏi:

1. Có bao nhiêu cập nhật CAS có thể khớp và tăng version từ 10 lên 11 trong cuộc cạnh tranh này?
2. Request thua cuộc nhận `matchedCount` bao nhiêu?
3. Có nên tự retry B với version 11 và giá 120000 mà không hỏi người dùng không?

**Gợi ý:** chỉ một thao tác có thể thành công ở version 10. Một request có thể đọc lại dữ liệu và quyết định retry theo chính sách; nếu hai người cùng sửa **một field giá**, việc ghi đè tự động thường cần được cân nhắc kỹ.

### 17.2. Tình huống B: giá và mô tả là hai field độc lập

A sửa giá, B sửa mô tả dựa trên cùng snapshot. Sau khi A lưu, B nhận conflict. Hãy xây chính sách cho phép B tải version mới và áp lại **chỉ field description**, đồng thời không thay đổi giá A đã lưu.

Tự trả lời: vì sao gửi lại toàn bộ document cũ có thể làm mất giá mới? Điều kiện nào khiến một patch tưởng như độc lập thực ra không an toàn?

### 17.3. Tình huống C: document bị xóa

Client giữ `expectedVersion:5`. Trong khi người dùng chỉnh, một admin xóa document. CAS theo `_id + version` trả `matchedCount:0`. Nếu server chỉ nhìn kết quả này, có thể báo nhầm loại lỗi gì? Nên tra cứu lại như thế nào mà vẫn không lộ tài nguyên ngoài tenant?

### 17.4. Tình huống D: hàng tồn kho

Document có `quantity:3`. Hai request cùng muốn trừ 2.

- Nếu dùng `findOne` rồi tính và `$set`, vì sao có thể ghi sai?
- Nếu dùng `updateOne({quantity:{$gte:2}},{$inc:{quantity:-2}})`, điều kiện bảo vệ điều gì?
- Nếu một request bị client phát lại sau timeout, tại sao điều kiện quantity vẫn chưa đủ thay thế operation ID/idempotency?

### 17.5. Tình huống E: transaction và side effect

Một request phê duyệt đơn hàng, trừ inventory ở document khác và gửi email. Hãy nêu:

- Phần nào có thể đưa vào MongoDB transaction?
- Phần nào cần outbox/idempotent consumer?
- Vì sao chỉ tăng `order.version` không bảo vệ toàn bộ quy trình?

## 18. Dọn dữ liệu thực hành an toàn

Các ví dụ ở mục 4 chỉ thêm một document trong collection thử nghiệm `mongo_occ_row216_lab.products_demo`. Trước khi xóa, hãy xác nhận database và ID đã tạo trong **chính phiên `mongosh`**:

```javascript
print("database=" + lab.getName());
print("collection=" + products.getName());
print("runId=" + runId);
printjson(
  products.findOne(
    { _id: productId, runId },
    { _id: 1, runId: 1, sku: 1, version: 1 }
  )
);
```

Nếu đúng là document do mình tạo, xóa bằng filter chứa **cả ID và runId**:

```javascript
const removed = products.deleteOne({
  _id: productId,
  runId
});

printjson(removed);
print("remaining=" + products.countDocuments({
  _id: productId,
  runId
}));
```

Nếu document không khớp hoặc `runId` không còn xác định được, dừng để kiểm tra quyền sở hữu dữ liệu. Không dùng `deleteMany({})`, `drop()` hoặc `dropDatabase()` trong môi trường chia sẻ.

## 19. Câu hỏi ôn tập

1. Lost update xảy ra như thế nào khi hai request cùng đọc một document?
2. MongoDB bảo đảm một `updateOne` nguyên tử có đồng nghĩa chuỗi `findOne` rồi `updateOne` cũng nguyên tử không?
3. Vì sao phải đưa `version` vào filter chứ không chỉ đặt nó trong payload cập nhật?
4. Vì sao cần tăng version trong **cùng** thao tác CAS?
5. `matchedCount:0` có phải luôn là conflict do version hay không?
6. Vì sao không được bật `upsert:true` khi update theo version cũ?
7. Khi nào một patch có thể được rebase tự động? Khi nào cần người dùng hòa giải?
8. Vì sao index `{version:1}` thường không cần thiết khi mỗi CAS đã lọc theo `_id`?
9. Khi nào dùng `findOneAndUpdate` thuận tiện hơn `updateOne`?
10. Tại sao timeout sau lệnh ghi có thể dẫn đến trạng thái chưa rõ dù đọc thấy version mới?
11. Driver retryable writes khác với idempotency của API ở điểm nào?
12. Version một document có thể bảo vệ tính nguyên tử của nhiều document khác không?
13. Vì sao update stock bằng `$inc` có thể tránh lost update trong một số trường hợp mà không cần OCC?
14. Tại sao mọi writer, kể cả migration và background job, phải theo chung giao thức?
15. Khi một document chứa hàng nghìn phần tử con, dùng một version toàn document có ưu và nhược điểm gì?
16. ETag/If-Match có quan hệ gì với expectedVersion và phản hồi HTTP `412`?

## 20. Kết luận

**Khóa lạc quan bằng trường `version`** là một mẫu kiểm soát cạnh tranh trên MongoDB: **đọc document kèm version → gửi thay đổi với expectedVersion → cập nhật nguyên tử khi version còn khớp → tăng version cùng lần ghi**. Nhờ đó, một request dựa trên dữ liệu cũ có thể được nhận diện thay vì âm thầm ghi đè thay đổi của request khác.

OCC không tự quyết định cách hòa giải xung đột. Ứng dụng phải phân biệt **conflict**, **not found**, **điều kiện nghiệp vụ không còn đúng** và **kết quả ghi chưa xác định**; chọn báo người dùng, đọc lại/merge hoặc retry có giới hạn theo semantics của thao tác. Mọi writer phải giữ chung quy ước version, và các tác vụ đa document hoặc có side effect cần thêm transaction, unique constraint và idempotency khi thích hợp. **Version giúp tránh lost update, nhưng tính đúng đắn cuối cùng phụ thuộc vào cả mô hình dữ liệu lẫn quy trình nghiệp vụ.**
