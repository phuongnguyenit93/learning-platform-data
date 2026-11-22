# Xử lý thành công một phần, gửi lại có chọn lọc và chống ghi trùng trong MongoDB

## 1. Vì sao ghi theo lô không đồng nghĩa với “tất cả cùng thành công”?

Giả sử một ứng dụng nhập 5.000 đơn hàng từ hệ thống đối tác vào MongoDB. Để giảm số lần giao tiếp với database, ứng dụng gom nhiều thao tác và gọi `bulkWrite()`. Trong số đó có một đơn hàng trùng khóa, một document sai schema, còn phần lớn đơn hàng hợp lệ.

Kết quả nào đúng?

- Không thể mặc định “cả lô thất bại” chỉ vì API trả lỗi.
- Không thể mặc định “cả lô thành công” chỉ vì một số thao tác đã được ghi.
- Không thể gửi lại nguyên lô một cách mù quáng nếu những thao tác trước đó có thể tạo thêm bản ghi, trừ tiền, tăng số lượng hoặc xóa dữ liệu không mong muốn.

**Thành công một phần** (*partial success*) nghĩa là một số thao tác trong lô đã có hiệu lực, trong khi thao tác khác lỗi hoặc chưa được thực hiện. Điều này có thể xảy ra ở thao tác ghi theo lô ngoài transaction, đặc biệt khi có lỗi như duplicate key hoặc document validation.

Để xử lý đúng, ứng dụng cần kết hợp:

1. **Hiểu kết quả của `bulkWrite()`**, nhất là khác biệt giữa `ordered: true` và `ordered: false`.
2. **Gắn định danh ổn định cho từng tác vụ** để nhận ra thao tác nào đã hoàn thành, thao tác nào lỗi và thao tác nào chưa rõ kết quả.
3. **Phân loại lỗi và gửi lại có chọn lọc**, thay vì retry vô hạn mọi thao tác.
4. **Thiết kế thao tác có tính idempotent** để một yêu cầu được xử lý lại không làm tăng thêm tác dụng ngoài dự định.
5. **Dùng unique index** bảo vệ quy tắc không trùng khóa ở MongoDB khi nhiều worker chạy đồng thời.
6. **Đối soát kết quả sau lỗi mạng hoặc write concern**, bởi khi không nhận được phản hồi, trạng thái ghi có thể chưa xác định.

Bài học thuộc phần **Xóa và ghi theo lô** của MongoDB, nên các nguyên tắc sẽ được áp dụng cho cả `insertOne`, `updateOne`, `deleteOne`, `updateMany` và `deleteMany` bên trong lô.

## 2. Cơ chế cơ bản của `bulkWrite()`

### 2.1. Một lô có thể chứa những thao tác gì?

Ở mức collection, `bulkWrite()` nhận mảng các operation model:

```javascript
db.orders.bulkWrite([
  {
    insertOne: {
      document: {
        orderId: "O-001",
        status: "NEW"
      }
    }
  },
  {
    updateOne: {
      filter: { orderId: "O-002" },
      update: { $set: { status: "PAID" } }
    }
  },
  {
    deleteOne: {
      filter: { orderId: "O-003" }
    }
  }
], { ordered: true });
```

Các kiểu thao tác phổ biến là:

| Operation model | Ý nghĩa | Chú ý khi retry |
| --- | --- | --- |
| `insertOne` | Chèn một document | Nếu tạo `_id` mới mỗi lần, retry có thể gây bản ghi trùng nghiệp vụ |
| `updateOne` | Cập nhật tối đa một document khớp filter | Phụ thuộc update là `$set`, `$inc`, `$push`... |
| `updateMany` | Cập nhật mọi document khớp | Có thể ảnh hưởng nhiều document; khó xác định chi tiết sau lỗi |
| `replaceOne` | Thay thế một document; có thể upsert | Cần khóa nghiệp vụ ổn định và kiểm tra payload |
| `deleteOne` | Xóa tối đa một document | Retry theo `_id` cố định có thể đạt cùng trạng thái cuối |
| `deleteMany` | Xóa mọi document khớp | Filter rộng có thể bắt thêm document mới vào lần retry |

`bulkWrite()` giúp gom các operation để giảm chi phí gửi lệnh và hỗ trợ một số tối ưu thực thi. Tuy nhiên, **nhiều thao tác trong một bulk không tự trở thành một transaction nguyên tử**. Khi không dùng transaction, tính nguyên tử thông thường của MongoDB áp dụng ở phạm vi **một document** cho một thao tác ghi, kể cả khi thao tác cập nhật nhiều field của document đó.

### 2.2. `ordered: true` và `ordered: false` khác nhau ra sao?

Giả sử một lô gồm:

```text
Vị trí trong input:   0        1          2        3
Operation:           A        B          C        D
Tình trạng:         tốt    duplicate    tốt      tốt
```

**`ordered: true`** (mặc định): MongoDB thực hiện theo thứ tự đã cung cấp và dừng xử lý lô tại **lỗi ghi** đầu tiên. Nếu A thành công và B lỗi, các thao tác C, D phía sau B trong lô thường chưa được thực hiện.

**`ordered: false`**: MongoDB cố gắng tiếp tục những operation khác dù một operation gặp lỗi. A, C và D có thể thành công trong khi B thất bại. Server có quyền tổ chức thực thi để tối ưu; **không dựa vào thứ tự thực thi thực tế** trong unordered bulk để lập quy tắc nghiệp vụ.

| Đặc điểm | `ordered: true` | `ordered: false` |
| --- | --- | --- |
| Khi một operation gặp write error | Dừng tại lỗi đầu tiên trong luồng có thứ tự | Cố xử lý những operation còn lại |
| Bảo đảm thứ tự theo input | Có, theo ngữ nghĩa ordered | Không |
| Phù hợp | Các thao tác phải chạy theo thứ tự, dễ nhận biết phần chưa thử | Các operation tương đối độc lập |
| Khi xử lý lỗi | Xét cả phần đã thực hiện và phần đuôi chưa thực hiện | Xét lỗi từng operation và đối soát những operation còn lại |
| Có bảo đảm cả lô nguyên tử? | Không | Không |

**Quan trọng:** `ordered: false` không có nghĩa “bất kể lỗi gì server cũng xử lý được mọi operation”. Lỗi mạng, gián đoạn server, vấn đề toàn lệnh hoặc write concern có thể khiến kết quả chưa rõ. Thông tin về từng lỗi ghi chỉ đáng tin trong phạm vi server/driver đã báo cáo.

### 2.3. Bulk lớn có thể được driver chia thành nhiều nhóm bên trong

Driver và server có giới hạn số lượng operation và kích thước message. Khi mảng lớn, driver có thể chia thành các batch nhỏ để gửi. Vì vậy không nên suy luận một lệnh `bulkWrite()` lớn sẽ tương ứng với đúng một thông điệp mạng hoặc một đơn vị commit.

Nếu xảy ra lỗi sau khi một số batch con đã được thực hiện, lô có thể có kết quả một phần. Khi ghi log hoặc tái lập từ checkpoint, hãy giữ **chỉ số của operation trong danh sách input ban đầu** và khóa nghiệp vụ ổn định của nó. Driver có thể cung cấp chỉ số lỗi đã quy đổi về vị trí input, nhưng cách biểu diễn error object cần được đọc theo API của phiên bản driver đang dùng.

## 3. Đọc kết quả: điều gì đã xảy ra, điều gì chưa biết?

### 3.1. Kết quả khi bulk hoàn toàn không có lỗi

Một `BulkWriteResult` thường chứa các số liệu tổng hợp:

```javascript
{
  acknowledged: true,
  insertedCount: 3,
  matchedCount: 2,
  modifiedCount: 1,
  deletedCount: 1,
  upsertedCount: 1,
  insertedIds: { /* chỉ số input -> _id */ },
  upsertedIds: { /* chỉ số input -> _id */ }
}
```

Đây là **ví dụ minh họa hình dạng kết quả**, không phải output cố định cho mọi lô. Các field có thể khác tùy loại thao tác và API driver.

| Trường | Cách hiểu |
| --- | --- |
| `insertedCount` | Số operation chèn thành công theo kết quả báo cáo |
| `matchedCount` | Số document được các update/replace khớp |
| `modifiedCount` | Số document thực sự được thay đổi, có thể ít hơn `matchedCount` |
| `deletedCount` | Số document được xóa bởi các delete operation |
| `upsertedCount` | Số document được chèn từ các upsert |
| `insertedIds`, `upsertedIds` | ID tương ứng các operation được chèn/upsert, nếu API cung cấp |

Các con số tổng hợp **không phải bảng trạng thái cho từng nghiệp vụ**. Ví dụ `matchedCount: 1` không đủ cho biết **đơn hàng nào** đã được cập nhật nếu lô có nhiều operation. Nếu cần đối soát từng item, phải giữ danh sách đầu vào và định danh của từng item.

### 3.2. Phân biệt ba lớp lỗi

| Nhóm lỗi | Ví dụ | Điều có thể và chưa thể kết luận |
| --- | --- | --- |
| **Write error của từng operation** | `E11000` duplicate key, lỗi document validation `121` | Có thể biết operation nào bị từ chối qua index; những operation khác có thể đã thành công |
| **Write concern error** | Không nhận được xác nhận ở mức yêu cầu, ví dụ timeout chờ replication | Ghi có thể đã được áp dụng ở một số node; chưa thể kết luận độ bền/xác nhận theo yêu cầu |
| **Network/server/timeout toàn lệnh** | Connection closed, server selection timeout, mất kết nối trước khi nhận response | Có thể không biết thao tác nào đã được server thực hiện; trạng thái là **chưa xác định** |

Lỗi duplicate key có mã MongoDB thường gặp là **`11000`**; document validation thất bại thường gặp **`121`**. Những lỗi này thông thường không hết chỉ vì gửi lại chính payload không hợp lệ.

**Write concern error khác write error:** một thao tác có thể đã sửa dữ liệu trên primary nhưng chưa đạt mức xác nhận mong muốn (chẳng hạn `w: "majority"` trong thời hạn). Nếu hệ thống cần bảo đảm commit được xác nhận theo write concern, đọc thấy dữ liệu trên primary sau đó chưa đủ để suy ra đã đạt mức bảo đảm từ lỗi ban đầu.

### 3.3. Vì sao không được suy luận “ném exception = không ghi gì”?

Một driver có thể ném `MongoBulkWriteError` trong khi trả kèm:

- số lượng operation đã thành công;
- một số write error gắn với **index** của operation;
- thông tin write concern error nếu có.

Ví dụ trên một lô unordered gồm ba `insertOne`:

```text
operation[0] A -> đã chèn
operation[1] B -> E11000
operation[2] C -> đã chèn

bulkWrite(...) -> ném lỗi do B
database        -> vẫn chứa A và C
```

Do đó không được đặt logic kiểu “nếu `bulkWrite` throw thì chạy lại cả mảng `insertOne` với ObjectId mới”. Kết quả có thể là A và C bị ghi lặp hoặc gây thêm lỗi trùng khóa.

## 4. Thực hành quan sát thành công một phần

### 4.1. Chuẩn bị collection thử nghiệm và khóa riêng

Ví dụ sau dùng `mongosh` trong database riêng là `mongo_bulk_row135_lab`. Chỉ chạy ở môi trường được phép thao tác. Trong phiên shell:

```javascript
const lab = db.getSiblingDB("mongo_bulk_row135_lab");
const orders = lab.getCollection("orders_demo");

const runId = "row135-" + new ObjectId().toHexString();
print("database=" + lab.getName());
print("runId=" + runId);

// Ràng buộc một sourceId chỉ xuất hiện một lần trong mỗi runId.
orders.createIndex(
  { runId: 1, sourceId: 1 },
  { unique: true, name: "uniq_run_source" }
);

// Chuẩn bị bản ghi B để tạo lỗi duplicate một cách có chủ đích.
orders.insertOne({
  runId,
  sourceId: "B",
  payloadDigest: "digest-original-B",
  status: "EXISTING",
  createdAt: new Date()
});
```

`runId` tách biệt dữ liệu mỗi lần thực hành. Ở hệ thống thật, một khóa nghiệp vụ ổn định thường là `{ tenantId, externalId }`, còn `runId` chỉ là dấu nhận diện của bài tập.

### 4.2. Ghi một bulk unordered có lỗi

```javascript
const operations = [
  {
    insertOne: {
      document: {
        runId,
        sourceId: "A",
        payloadDigest: "digest-A",
        status: "NEW"
      }
    }
  },
  {
    insertOne: {
      document: {
        runId,
        sourceId: "B",
        payloadDigest: "digest-new-B",
        status: "NEW"
      }
    }
  },
  {
    insertOne: {
      document: {
        runId,
        sourceId: "C",
        payloadDigest: "digest-C",
        status: "NEW"
      }
    }
  }
];

try {
  const result = orders.bulkWrite(operations, { ordered: false });
  printjson(result);
} catch (error) {
  print("Bulk error: " + error.message);
  // Cách expose writeErrors/result tùy phiên bản mongosh/driver;
  // in toàn bộ lỗi trong môi trường lab để quan sát.
  printjson(error);
}
```

Operation tại **index 1** cố chèn `B` đã tồn tại theo unique index nên bị từ chối. Với unordered bulk và server hoạt động bình thường, A và C vẫn có thể được ghi thành công. Lỗi của B không tự rollback A hoặc C.

Sau khi chạy, đối chiếu thực tế:

```javascript
printjson(
  orders.find(
    { runId },
    { _id: 0, runId: 0, sourceId: 1, payloadDigest: 1, status: 1 }
  ).sort({ sourceId: 1 }).toArray()
);
```

Thông thường kết quả chứa A, B gốc và C. B vẫn có `payloadDigest: "digest-original-B"`, không phải payload mới của operation bị từ chối. Đó là minh họa cho sự khác nhau giữa **một thao tác thành công** và **một thao tác bị chặn để bảo vệ dữ liệu**.

### 4.3. Nếu chuyển sang `ordered: true`

Nếu làm thử một lượt mới với khóa `runId` mới, tạo sẵn B rồi gửi A, B, C theo `ordered: true`, MongoDB sẽ dừng ở B. A có thể được chèn; C nằm sau lỗi và **chưa được thực hiện** trong luồng ordered.

Không được tái sử dụng một `runId` đã có A/C từ thử nghiệm unordered để suy luận kết quả ordered: khi đó tình trạng dữ liệu ban đầu đã khác, làm thay đổi điểm phát sinh lỗi.

## 5. Thiết kế một “định danh ổn định” cho từng thao tác

### 5.1. Định danh nghiệp vụ khác số thứ tự trong mảng

Một mảng đầu vào có `operations[2]` trong lần gửi đầu tiên, nhưng sau khi loại bỏ item đã hoàn thành, item tương tự có thể trở thành `operations[0]` trong lần gửi lại. Vì thế **index dùng để đối chiếu lỗi trong một lần gọi**, không nên là định danh nghiệp vụ lâu dài.

Một bản ghi import nên có khóa riêng, ví dụ:

```javascript
{
  tenantId: "TENANT-A",
  sourceSystem: "ERP",
  externalId: "ORD-2026-001",
  payloadDigest: "sha256-of-canonical-business-fields",
  payload: {
    amountCents: 125000,
    currency: "VND"
  }
}
```

Khóa nghiệp vụ có thể là:

```text
(tenantId, sourceSystem, externalId)
```

`payloadDigest` là fingerprint của các trường nghiệp vụ sau khi được chuẩn hóa; nó giúp phát hiện cùng khóa nhưng payload khác. Nếu dữ liệu cập nhật có **version** hoặc thời điểm hiệu lực, cần bổ sung quy tắc xử lý version cho đúng nghiệp vụ, thay vì coi mọi payload khác là lệnh tạo mới hợp lệ.

### 5.2. Lập danh sách tác vụ trước khi gửi

Một cấu trúc lưu checkpoint hoặc log công việc:

```text
Batch: IMPORT-2026-11-14-01

Item key                             State
-------------------------------------------------
TENANT-A / ERP / ORD-001             PENDING
TENANT-A / ERP / ORD-002             PENDING
TENANT-A / ERP / ORD-003             PENDING
```

Các trạng thái có thể dùng ở tầng ứng dụng:

| Trạng thái | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| `PENDING` | Chưa gửi hoặc đang chờ gửi | Đưa vào batch |
| `CONFIRMED` | Đã xác nhận hiệu quả nghiệp vụ như mong đợi | Không gửi lại |
| `RETRYABLE` | Lỗi tạm thời, thao tác có thể lặp an toàn | Retry có giới hạn và backoff |
| `CONFLICT` | Cùng khóa nhưng nội dung/quy tắc khác | Dừng, đối soát hoặc đưa người xử lý |
| `INVALID` | Dữ liệu sai schema, kiểu hoặc thiếu field | Sửa dữ liệu nguồn; không retry nguyên payload |
| `UNKNOWN` | Không biết chính xác kết quả ghi | Đối soát theo key/ID rồi quyết định |

Một trạng thái như `CONFIRMED` cần được hiểu theo **mức bảo đảm mà ứng dụng yêu cầu**. Nếu chỉ nhìn thấy document trên primary sau `wtimeout`, chưa chắc đã đạt xác nhận majority mà chính sách đòi hỏi.

### 5.3. Chống trùng ngay trong danh sách đầu vào

Trước khi xây `bulkWrite`, ứng dụng nên phát hiện **hai item cùng khóa trong một batch**. Nếu cùng khóa, cùng fingerprint thì có thể gộp theo chính sách. Nếu cùng khóa nhưng payload khác, phải quyết định thứ tự/version hoặc báo xung đột.

Đừng phụ thuộc MongoDB tự “chọn bản ghi đúng” khi một batch unordered chứa hai upsert mâu thuẫn cho cùng key: vì thứ tự có thể không được bảo đảm theo input, giá trị cuối cùng có thể phụ thuộc lịch thực thi.

## 6. Idempotency: retry không được lặp tác dụng nghiệp vụ

### 6.1. Phân biệt các kiểu thao tác

Một thao tác **idempotent** khi lặp lại với cùng dữ liệu/khóa vẫn cho trạng thái nghiệp vụ cuối tương đương với một lần xử lý.

| Thao tác | Có thể lặp an toàn? | Điều kiện quan trọng |
| --- | --- | --- |
| `$set: { status: "READY" }` | Thường có với giá trị cuối | Không được làm lùi state machine; cẩn thận `updatedAt` và side effect |
| `$setOnInsert` trong upsert theo unique key | Thường phù hợp để tạo một lần | Unique index, key ổn định, kiểm payload cũ |
| `insertOne` với `_id` cố định | Chặn trùng theo `_id` | Khi duplicate cần so sánh bản ghi hiện có, không coi mọi lỗi là thành công |
| `$inc: { stock: -1 }` | Không | Mỗi lần thành công lại giảm thêm |
| `$push: { events: event }` | Không theo mặc định | Mỗi lần thành công có thể thêm bản sao phần tử |
| `$addToSet` với cùng một giá trị | Có tính tránh phần tử trùng theo ngữ nghĩa mảng | Không thay thế unique index cho bản ghi nghiệp vụ |
| `deleteOne` theo `_id` cụ thể | Thường cho cùng trạng thái “không còn document” | Lần sau có `deletedCount: 0`; không có nghĩa lần đầu chưa xóa |
| `deleteMany` theo điều kiện rộng | Cần thận trọng | Item mới có thể khớp filter ở lần retry |

Ví dụ không idempotent:

```javascript
db.accounts.updateOne(
  { _id: "ACC-01" },
  { $inc: { balanceCents: -50000 } }
);
```

Nếu client timeout rồi chạy lại và cả hai lần ghi đều thành công, tiền bị trừ hai lần. Một unique index trên `accounts._id` **không bảo vệ** khỏi lặp `$inc` trên cùng document.

Nếu nghiệp vụ cần “trừ tiền một lần cho giao dịch X”, nên có bản ghi thao tác/giao dịch với ID duy nhất, cơ chế tránh xử lý lại và phối hợp cập nhật số dư theo một thiết kế có tính nhất quán, có thể yêu cầu transaction.

### 6.2. Dùng `$setOnInsert` với upsert và unique index

Với bài toán import đơn hàng, nên xây một document cho mỗi key:

```javascript
// Tạo unique index một lần trên collection thử nghiệm.
orders.createIndex(
  { runId: 1, sourceId: 1 },
  { unique: true, name: "uniq_run_source" }
);

// Một item mới của lượt thực hành.
const newKey = {
  runId,
  sourceId: "D"
};

const importResult = orders.updateOne(
  newKey,
  {
    $setOnInsert: {
      payloadDigest: "digest-D",
      status: "NEW",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(importResult);
```

Khi chưa có D, server chèn mới. Khi đã có D, `$setOnInsert` không thay đổi document cũ. **Unique index** là lớp bảo đảm một cặp `(runId, sourceId)` không được lưu hai lần, kể cả khi hai worker cùng gửi upsert.

Không có unique index, hai upsert đồng thời cùng không thấy document có thể cùng chèn, tùy lịch chạy. `upsert: true` một mình không tương đương ràng buộc duy nhất.

### 6.3. Khi trùng khóa, phải so sánh nội dung

Giả sử đã tồn tại:

```javascript
{
  runId: "row135-abc",
  sourceId: "D",
  payloadDigest: "digest-D",
  status: "PROCESSED"
}
```

Một yêu cầu lặp cùng khóa, cùng `payloadDigest` có thể được coi là cùng dữ liệu đầu vào đã tiếp nhận. Nhưng nếu payload mới có digest khác, việc trả “đã thành công” sẽ che xung đột dữ liệu. Quy trình cần:

1. Tìm document hiện tại theo đúng unique key.
2. So `payloadDigest` hoặc phiên bản nghiệp vụ và các trường quyết định ý nghĩa của yêu cầu.
3. Nếu tương đương, ghi nhận đã xử lý hoặc tiếp tục phần còn thiếu theo state machine.
4. Nếu khác, báo `CONFLICT` hoặc áp quy tắc cập nhật theo version được thiết kế trước.

**Lưu ý:** hash phải được tính từ biểu diễn chuẩn của những field nghiệp vụ quan trọng. Không lấy hash tùy ý do client gửi rồi tin rằng hai yêu cầu giống nhau. Không đưa thời điểm nhận request mới vào hash nếu nó không làm thay đổi ý nghĩa nghiệp vụ.

## 7. Gửi lại có chọn lọc: phân loại lỗi trước khi retry

### 7.1. Không phải lỗi nào cũng nên retry

| Kết quả | Nguyên nhân điển hình | Xử lý |
| --- | --- | --- |
| `11000` duplicate key | Item đã tồn tại hoặc va chạm index khác | Tra cứu đúng key, đối chiếu payload; xác nhận hoặc conflict |
| `121` document validation | Field thiếu, sai BSON type, enum không hợp lệ | Sửa dữ liệu/contract; đưa vào hàng lỗi, không retry nguyên payload |
| Lỗi phân quyền | Tài khoản không có quyền ghi/xóa | Sửa cấu hình hoặc quyền theo quy trình, không retry liên tục |
| Lỗi tạm thời được nhận diện | Thay đổi primary, lỗi mạng ngắn hạn, transient error phù hợp | Retry có giới hạn nếu thao tác idempotent và điều kiện cho phép |
| Write concern timeout/error | Có thể đã ghi nhưng chưa đạt mức xác nhận | Gắn `UNKNOWN`, đối soát theo chính sách read/write concern |
| Mất kết nối trước response | Không biết operation nào đã thực thi | Đối soát theo khóa; chỉ gửi lại khi an toàn |
| Filter không khớp lúc `updateOne` | Document đã đổi trạng thái hoặc không tồn tại | Kiểm tra quy tắc nghiệp vụ; không tự chuyển sang upsert |

Nguyên tắc thực hành: **lỗi dữ liệu vĩnh viễn cần sửa dữ liệu**, **xung đột cần đối chiếu**, **lỗi tạm thời mới đáng retry**, **kết quả chưa rõ cần reconcile**.

### 7.2. Ánh xạ lỗi về input index

Với một lô unordered có response lỗi ghi rõ ràng, thông tin `writeErrors` thường chỉ ra vị trí của operation bị lỗi trong mảng input. Ví dụ minh họa:

```text
Input:
 index 0 -> externalId A
 index 1 -> externalId B
 index 2 -> externalId C
 index 3 -> externalId D

writeErrors:
 { index: 1, code: 11000 }
 { index: 3, code: 121 }
```

Ta dùng ánh xạ `index → business key` của **lần gọi đó**:

```text
B -> duplicate: cần tìm bản ghi hiện có và đối chiếu
D -> invalid: đưa vào nhóm cần sửa dữ liệu
A, C -> không có lỗi theo từng item được báo cáo
```

Không có write error ở A, C **chưa đủ** để khẳng định mọi điều kiện xác nhận/độ bền đều được thỏa mãn nếu toàn lệnh đồng thời có write concern error hoặc kết quả không đầy đủ. Với response được xác nhận đầy đủ, có thể sử dụng kết quả bulk để ghi nhận tiến độ; khi cần bảo đảm theo từng item, đối chiếu thêm bằng khóa hoặc log xử lý.

Với `ordered: true`, nếu B ở index 1 lỗi thì C, D ở phía sau chưa được gửi/thi hành trong luồng ordered. Chúng không phải “thành công vì không có trong `writeErrors`”. Khi lập kế hoạch gửi lại, phải phân biệt **failed** và **not attempted**.

### 7.3. Mẫu thuật toán gửi lại

```text
Lưu snapshot danh sách input + khóa nghiệp vụ + fingerprint
                       |
                       v
                  Gửi bulk
                       |
         +-------------+--------------+
         |             |              |
         v             v              v
   Có xác nhận    Có write error   Kết quả không rõ
   đầy đủ         từng item        / write concern
         |             |              |
         v             v              v
   Đánh dấu    Ánh xạ theo index   UNKNOWN, đối soát
   đã xử lý    rồi phân loại       theo khóa
                       |              |
              +--------+----+         |
              |             |         |
              v             v         v
        NON-RETRYABLE   RETRYABLE  Xác minh trạng thái
        → sửa/conflict  → backoff   rồi quyết định retry
              |             |         |
              +-------------+---------+
                            |
                            v
                     Lưu checkpoint
```

**Đừng biến lỗi `E11000` thành lệnh insert lại với `_id` mới.** Nếu dữ liệu đã tồn tại theo khóa nghiệp vụ, thao tác retry như thế không giải quyết được lỗi và có thể che vấn đề sai mô hình.

## 8. Ví dụ Node.js: xây bulk có thể lặp an toàn

Ví dụ sau dùng MongoDB Node.js driver. Nó minh họa **import chỉ tạo nếu chưa có**, với cùng external ID thì giữ bản ghi đầu tiên, không ghi đè trạng thái nghiệp vụ. Giả định:

- `tenantId` do server xác định từ ngữ cảnh tin cậy.
- `externalId`, `payloadDigest` và `amountCents` đã được kiểm tra/chuẩn hóa.
- Collection có unique index `{ tenantId: 1, externalId: 1 }`.
- Mỗi item trong lô có external ID khác nhau; nếu đầu vào trùng key, ứng dụng xử lý trùng từ trước.

### 8.1. Dựng danh sách operation

```javascript
function buildImportOperations(tenantId, items, acceptedAt) {
  const seen = new Set();

  return items.map((item) => {
    if (seen.has(item.externalId)) {
      throw new Error("Duplicate externalId inside input batch");
    }
    seen.add(item.externalId);

    return {
      updateOne: {
        filter: {
          tenantId,
          externalId: item.externalId
        },
        update: {
          $setOnInsert: {
            payloadDigest: item.payloadDigest,
            amountCents: item.amountCents,
            status: "RECEIVED",
            createdAt: acceptedAt
          }
        },
        upsert: true
      }
    };
  });
}
```

Trong ví dụ, `acceptedAt` được tạo một lần cho một batch và truyền vào hàm, thay vì thay đổi tùy ý mỗi khi xây lại operation. Khi chỉ tạo mới, `$setOnInsert` giúp retry không sửa lại document đã có. Nếu cần đồng bộ cập nhật, phải bổ sung những field có thể `$set` và quy tắc version riêng.

Tạo index một lần theo quy trình khởi tạo/migration:

```javascript
await db.collection("importOrders").createIndex(
  { tenantId: 1, externalId: 1 },
  { unique: true, name: "uniq_tenant_external" }
);
```

### 8.2. Gửi unordered bulk và giữ lại lỗi kỹ thuật

```javascript
async function sendImportBulk(collection, tenantId, items, acceptedAt) {
  const operations = buildImportOperations(tenantId, items, acceptedAt);

  try {
    const result = await collection.bulkWrite(
      operations,
      { ordered: false, writeConcern: { w: "majority" } }
    );
    return { result, error: null, operations };
  } catch (error) {
    // Bulk có thể đã ghi một phần; giữ error để đối soát.
    return { result: error?.result ?? null, error, operations };
  }
}
```

`error.writeErrors` của MongoDB driver thường chứa lỗi gắn với input index; `error.result` có thể chứa kết quả một phần. Kiểu cấu trúc, field và metadata cụ thể cần được đọc theo phiên bản driver. Đoạn hàm này **chưa trả kết luận cho từng item**; nó giữ đủ ngữ cảnh để bước đối soát quyết định.

Với lô có `updateMany` hoặc `deleteMany`, khả năng retryable writes tự động của driver không giống các thao tác single-document. Không tự giả định mọi bulk đều được driver retry; cần xem các operation trong lô và cấu hình cụm MongoDB.

### 8.3. Đối soát bằng khóa nghiệp vụ

Sau một lỗi không rõ kết quả hoặc lỗi từng item, có thể đối chiếu lại **trạng thái đang lưu**. Ví dụ một batch cùng tenant:

```javascript
async function reconcileImport(collection, tenantId, items) {
  const ids = items.map((item) => item.externalId);

  const docs = await collection
    .find({
      tenantId,
      externalId: { $in: ids }
    })
    .project({
      _id: 0,
      externalId: 1,
      payloadDigest: 1
    })
    .toArray();

  const byId = new Map(
    docs.map((doc) => [doc.externalId, doc])
  );

  return items.map((item) => {
    const doc = byId.get(item.externalId);
    if (!doc) {
      return {
        externalId: item.externalId,
        state: "UNKNOWN_OR_MISSING"
      };
    }
    if (doc.payloadDigest !== item.payloadDigest) {
      return {
        externalId: item.externalId,
        state: "CONFLICT"
      };
    }
    return {
      externalId: item.externalId,
      state: "PRESENT_WITH_EXPECTED_PAYLOAD"
    };
  });
}
```

Điểm cần đọc đúng:

- `PRESENT_WITH_EXPECTED_PAYLOAD` xác nhận có document đúng khóa và fingerprint **ở thời điểm đọc**. Đây là bước quan sát hữu ích, nhưng nếu bulk có write concern error thì chưa tự chứng minh đã đạt mức xác nhận/durability yêu cầu.
- `CONFLICT` cho biết cùng khóa đang chứa payload khác; phải điều tra hoặc áp policy version, không được ghi đè bừa bãi.
- `UNKNOWN_OR_MISSING` chưa cho biết chắc chắn operation chưa từng được thực thi. Có thể có gián đoạn, xóa hoặc thay đổi đồng thời; cần xem nguyên nhân và chính sách retry.

Để đối soát có tính nhất quán theo yêu cầu, chọn read preference/read concern và write concern phù hợp với hệ thống. Trong ứng dụng nhỏ, đọc theo primary thường là điểm bắt đầu phù hợp; với nghiệp vụ cần đa số node xác nhận, không được đánh đồng “primary đọc thấy” với một lần ghi đã được majority acknowledge.

### 8.4. Đọc `writeErrors` và xây danh sách retry

Mẫu dưới đây thể hiện cách ánh xạ lỗi về từng item **khi driver đã trả về write error có chỉ số đầy đủ**:

```javascript
function classifyReportedWriteErrors(error, items) {
  const writeErrors = error?.writeErrors ?? [];
  const normalized = writeErrors instanceof Map
    ? [...writeErrors.values()]
    : writeErrors;

  return normalized.map((writeError) => {
    const item = items[writeError.index];
    const code = writeError.code;

    return {
      index: writeError.index,
      externalId: item?.externalId,
      code,
      decision:
        code === 11000 ? "RECONCILE_DUPLICATE" :
        code === 121 ? "INVALID_INPUT" :
        "INVESTIGATE_BEFORE_RETRY"
    };
  });
}
```

Hàm chỉ phân loại **write error được báo cáo**, chưa tự gán mọi operation không có trong mảng lỗi là thành công. Mã lỗi không quen thuộc có thể là lỗi tạm thời hoặc lỗi vĩnh viễn; phải hiểu nguyên nhân trước khi đưa vào hàng retry.

Với một lỗi có tính tạm thời và operation idempotent, có thể xây **batch mới chỉ gồm các item cần retry**. Batch mới có các input index mới; tiếp tục giữ external ID và digest làm khóa đối chiếu, không tái sử dụng index cũ như định danh nghiệp vụ.

### 8.5. Vì sao không nên đặt `$inc` hoặc `$push` vào bộ retry mẫu?

Nếu một item của bulk đã được áp dụng, nhưng response bị mất, retry `$inc` hay `$push` có thể lặp tác động. Một lô import đảm bảo tồn tại với `$setOnInsert` dễ gửi lại hơn nhiều.

Đối với cập nhật có tác động tích lũy, giải pháp thường cần **operation ID duy nhất và trạng thái đã xử lý**. Ví dụ một lệnh trừ số lượng tồn kho phải gắn với mã đơn hàng/giao dịch, được ghi nhận một lần và phối hợp với cập nhật tồn kho, có thể qua transaction hoặc một thiết kế document có điều kiện tương đương.

## 9. Xử lý các tình huống lỗi cụ thể

### 9.1. Duplicate key `11000`

**Dấu hiệu:** server từ chối insert hoặc upsert vì unique index bị vi phạm.

Các câu hỏi phải trả lời:

1. Index nào báo trùng? Có đúng là index bảo vệ khóa nghiệp vụ mong đợi?
2. Document theo khóa đó có tồn tại và thuộc tenant phù hợp không?
3. `payloadDigest` và version có khớp request đang được xử lý không?
4. Nếu khác nhau, policy là báo conflict, hợp nhất hay cập nhật theo version?

Nếu cùng khóa, cùng payload và thao tác có semantics “ensure exists”, có thể ghi nhận item đã được tiếp nhận. Nếu payload khác, không coi lỗi trùng là thành công. Tránh log lộ toàn bộ document nhạy cảm.

### 9.2. Document validation `121`

Ví dụ schema yêu cầu `amountCents` là BSON số nguyên không âm, nhưng import gửi `"125000"` dưới dạng string. MongoDB có thể từ chối document do validation. Gửi lại cùng string không khắc phục lỗi.

Thao tác phù hợp:

- ghi item lỗi vào báo cáo/hàng cần sửa kèm mã nguồn và lý do;
- sửa parser hoặc chuẩn hóa ở ứng dụng;
- chỉ gửi lại sau khi payload đã đúng hợp đồng schema;
- không tùy ý tắt validator để nhập nhanh.

### 9.3. Network timeout hoặc connection reset

Khi client không biết server đã nhận/ghi bao nhiêu operation, **không thể coi tất cả đều thất bại**. Gắn trạng thái chưa xác định, tra cứu theo key, kiểm fingerprint và retry bằng thao tác idempotent nếu cần.

Driver MongoDB hỗ trợ retryable writes ở các điều kiện nhất định, nhưng không thay thế idempotency cấp nghiệp vụ. Client/API có thể tạo request mới sau một timeout, queue có thể phát lại một message, và worker có thể chết giữa bước ghi dữ liệu với bước ghi nhận checkpoint.

### 9.4. Write concern timeout

Một thao tác có thể đã được áp dụng nhưng chưa đạt `w: "majority"` trong thời hạn. Không diễn giải `writeConcernError` thành “MongoDB rollback tất cả”. Cần quản lý trạng thái chưa chắc chắn theo mức bảo đảm mong muốn, theo dõi topology và đối soát trước khi tuyên bố hoàn tất.

### 9.5. Ordered bulk dừng ở thao tác thứ N

Nếu lô ordered có lỗi ghi tại index N, các operation trước đó có thể đã thành công, operation N lỗi, còn phần đuôi sau N chưa được thực hiện. Trong trường hợp có báo cáo lỗi rõ ràng, có thể tạo một lô mới từ phần chưa thực hiện sau khi xử lý operation gây lỗi.

Đừng gửi lại toàn bộ bằng thao tác không idempotent. Nếu lỗi toàn lệnh hoặc connection bị mất thì không áp dụng mù quáng quy tắc “phần đuôi chưa thực hiện”; khi đó cần đối soát trạng thái.

## 10. Xóa theo lô: retry an toàn bắt đầu từ phạm vi xóa

### 10.1. Phân biệt `deleteOne` và `deleteMany`

Giả sử bạn muốn dọn 100 document thử nghiệm theo danh sách ID đã xác định. Một batch gồm 100 `deleteOne` với `_id` cố định có đặc điểm hữu ích:

- Lần đầu xóa một document thành công, lần sau cùng filter sẽ không tìm thấy document đó; trạng thái “không còn document” vẫn giữ nguyên.
- `deletedCount: 0` ở lần retry **không cho biết** lần trước chưa từng xóa: có thể nó đã bị xóa trước đó.
- Nếu cần audit “xóa đúng một lần”, phải có sổ ghi nhận thao tác/định danh công việc, không chỉ dựa vào số lượng document xóa trong lần gọi hiện tại.

Ngược lại:

```javascript
db.events.deleteMany({
  createdAt: { $lt: new Date() }
});
```

Bộ lọc ở đây có thể thay đổi giữa các lần chạy vì `new Date()` tạo mốc mới. Một lần retry có thể xóa **thêm document mới** mà lần đầu không thuộc phạm vi. Đây là ví dụ vì sao retry một thao tác “xóa theo điều kiện rộng” có thể không giữ nguyên ý nghĩa nghiệp vụ.

### 10.2. Chụp snapshot danh sách đích trước khi xóa

Với dữ liệu thử nghiệm, có thể lấy các `_id` cụ thể rồi tạo lô `deleteOne` theo những ID đó:

```javascript
// Chỉ dùng trong database bài thực hành, với runId của chính bạn.
const targetIds = orders.find(
  { runId },
  { _id: 1 }
).toArray().map((doc) => doc._id);

const deleteOperations = targetIds.map((id) => ({
  deleteOne: {
    filter: { _id: id, runId }
  }
}));

print("candidateCount=" + deleteOperations.length);
```

Lợi ích: mỗi operation xóa chỉ nhắm vào một `_id` đã xem trước, kèm `runId` xác nhận quyền sở hữu dữ liệu test. Đừng vội chạy lệnh xóa trong môi trường chia sẻ khi chưa xem danh sách.

Khi đã xác nhận đó là **dữ liệu thử nghiệm do mình tạo**:

```javascript
if (deleteOperations.length > 0) {
  try {
    printjson(orders.bulkWrite(
      deleteOperations,
      { ordered: false }
    ));
  } catch (error) {
    print("Bulk delete error: " + error.message);
    printjson(error);
  }
}

// Đối chiếu lại các ID trong danh sách snapshot.
print("remainingFromSnapshot=" + orders.countDocuments({
  _id: { $in: targetIds },
  runId
}));
```

Nếu còn ID nào thuộc snapshot, cần xác định trạng thái và lý do lỗi trước khi retry **chỉ những ID còn cần xử lý**. Không thay `_id` bằng filter rộng `{}` hoặc `deleteMany({})` để cố xóa “cho hết”.

**Giới hạn mô hình:** nếu document bị xóa rồi một tiến trình khác tạo lại document có cùng `_id`, retry lệnh xóa theo `_id` có thể ảnh hưởng bản ghi mới đó. Với nghiệp vụ có thể tái sử dụng ID, cần thêm điều kiện nhận diện phiên bản hoặc thiết kế tombstone/operation log phù hợp. `_id` chỉ là khóa định danh, không tự bảo đảm toàn bộ vòng đời nghiệp vụ.

### 10.3. Trường hợp cần xóa hàng loạt theo điều kiện

Khi phải xóa dữ liệu quá hạn, cần **chốt phạm vi**:

- xác định mốc cutoff một lần cho cả chiến dịch, không tính lại theo thời điểm của từng retry;
- xác định điều kiện tenant, loại dữ liệu, trạng thái và yêu cầu lưu trữ pháp lý;
- lưu batch ID, cutoff, số lượng dự kiến và checkpoint;
- chia lô theo ID/cursor hoặc phương pháp phù hợp với kích thước dữ liệu và index;
- đo/xác nhận kết quả sau mỗi lô.

Với thao tác xóa thật sự quan trọng, cân nhắc soft delete, lưu lịch sử và quy trình phê duyệt riêng. Những lựa chọn này phụ thuộc nghiệp vụ; không nên suy ra lệnh `deleteMany` có rollback cả lô chỉ vì nó là một lời gọi.

## 11. Cạnh tranh giữa nhiều worker: unique index và trạng thái công việc

### 11.1. Hai worker cùng gửi một item

```text
             Worker A                   Worker B
                |                          |
                v                          v
        upsert externalId=X         upsert externalId=X
                |                          |
                +------------+-------------+
                             |
                             v
                  Unique index ở MongoDB
                             |
                   Tối đa một khóa X
```

Với upsert theo khóa unique và `$setOnInsert`, kết quả có thể là một worker chèn, worker còn lại thấy document đã có hoặc gặp `E11000`. Một số điều kiện cho phép upsert cạnh tranh chuyển sang nhánh cập nhật khi bộ lọc equality phù hợp khóa unique và cập nhật không thay đổi khóa; **không nên giả định mọi cạnh tranh đều tự trở thành update thành công**.

Ứng dụng cần đọc kết quả và lỗi, rồi xác nhận document hiện có đúng payload/version.

### 11.2. Claim một công việc bằng update có điều kiện

Nếu các worker lấy việc từ collection `jobs`, có thể dùng một thao tác `findOneAndUpdate` với filter trạng thái phù hợp để **claim** một job:

```javascript
const claimed = db.jobs.findOneAndUpdate(
  {
    state: "READY"
  },
  {
    $set: {
      state: "PROCESSING",
      workerId: "worker-01",
      claimedAt: new Date()
    }
  },
  {
    sort: { createdAt: 1 },
    returnDocument: "after"
  }
);
```

Đây là thao tác thay đổi trạng thái một document theo điều kiện và có tính nguyên tử ở phạm vi document được chọn. Với job queue thực tế, cần bổ sung **lease**, thời hạn claim, heartbeat, retry counter và quy tắc phục hồi khi worker chết. Không để job mắc kẹt vĩnh viễn ở `PROCESSING` nếu worker không còn hoạt động.

Ngay cả khi claim có điều kiện, vẫn có khả năng xử lý lại do lease hết hạn hoặc tác vụ bị phát lại. Vì thế **ghi dữ liệu đích phải có bảo vệ idempotency**.

### 11.3. Retry với backoff và giới hạn số lần

Nếu một item được xác định là retryable, sử dụng:

- số lần thử `attempt`, thời gian thử gần nhất;
- backoff tăng dần và jitter để tránh nhiều worker cùng retry một lúc;
- giới hạn thời gian/số lần thử;
- hàng lỗi cuối (*dead-letter queue*) hoặc trạng thái `FAILED_PERMANENTLY` khi không thể tự phục hồi;
- cảnh báo khi số item `UNKNOWN` hoặc `RETRYABLE` vượt ngưỡng.

Không cần đặt mọi lỗi vào vòng lặp retry liên tục. Lỗi dữ liệu sai, duplicate conflict thực sự hoặc thiếu quyền thường cần quyết định khác.

## 12. Khi nào cần transaction thay cho bulk thông thường?

### 12.1. Yêu cầu “tất cả hoặc không gì cả”

Nếu nghiệp vụ yêu cầu **cả nhóm thao tác phải cùng commit**, ví dụ:

- chuyển tiền giữa hai tài khoản;
- tạo order và trừ tồn kho như một bất biến;
- ghi nghiệp vụ và bản ghi outbox phải nhất quán;

thì chỉ dùng `bulkWrite()` ngoài transaction chưa đủ. MongoDB hỗ trợ transaction đa document trong topology phù hợp (như replica set hoặc sharded cluster). Trong transaction, các thao tác ghi thuộc cùng transaction được commit hoặc hủy cùng nhau theo ngữ nghĩa giao dịch.

Tuy nhiên, transaction không tự tạo:

- unique constraint nếu thiếu unique index;
- idempotency key cho request được gửi lại thành transaction mới;
- bảo đảm “email chỉ gửi một lần” nếu gửi email ngoài database;
- sự đúng đắn của filter và state machine.

### 12.2. Khác biệt về retry trong transaction

Một transaction có thể thất bại do write conflict, lỗi tạm thời hoặc kết quả commit chưa rõ. Cách retry transaction/commit phải dựa trên hướng dẫn driver và nhãn lỗi liên quan, tránh lặp side effect ngoài database trong callback có thể chạy lại.

Không mặc định “cứ bọc bulk vào transaction là mọi trường hợp lỗi thành công một phần biến mất khỏi hệ thống”: một request có thể đã commit nhưng client không nhận được phản hồi commit; ứng dụng vẫn cần idempotency khi client gọi lại thao tác nghiệp vụ.

### 12.3. Chọn giải pháp theo mức bảo đảm cần thiết

| Yêu cầu | Giải pháp thường phù hợp |
| --- | --- |
| Import nhiều record độc lập; chấp nhận item lỗi riêng | `bulkWrite` unordered, unique key, checkpoint và selective retry |
| Ghi tuần tự một chuỗi update có phụ thuộc | Ordered bulk hoặc transaction tùy invariant |
| Ghi một document đúng trạng thái | `updateOne` có filter trạng thái/version |
| Chỉ tạo một record cho mỗi external ID | Unique index và idempotent upsert |
| Cập nhật nhiều document phải cùng thành công | Transaction đa document |
| Xóa nhiều record đã biết ID và có thể retry | Các `deleteOne` có filter ID/ownership cố định và đối soát |
| Phát một event sang hệ ngoài đúng ngữ nghĩa | Outbox/inbox/idempotent consumer và xử lý delivery riêng |

## 13. Theo dõi tiến độ và khôi phục sau khi worker chết

### 13.1. Không chỉ giữ tiến độ trong RAM

Giả sử một worker vừa nhận response bulk thành công nhưng chết trước khi ghi checkpoint vào hệ thống điều phối. Khi khởi động lại, job có thể quay về `PENDING`. Nếu không có key ổn định và write idempotent, import lặp sẽ tạo trùng.

Vì thế nên lưu tiến độ bền vững theo **batch ID và item key** trong database hoặc hệ thống queue phù hợp. Các bước có thể là:

```text
Đọc các item PENDING/RETRYABLE
             |
             v
Xây operations từ snapshot dữ liệu nguồn
             |
             v
bulkWrite (ordered false nếu độc lập)
             |
             v
Phân loại result / error / unknown
             |
             v
Đối soát theo business key và fingerprint
             |
             v
Ghi checkpoint từng item
             |
             v
Chỉ xếp lại item cần retry
```

Việc lưu checkpoint cũng có thể bị lỗi hoặc cạnh tranh. Đây là lý do **nguồn sự thật cuối cùng** thường phải là ràng buộc unique và trạng thái dữ liệu đích, còn checkpoint hỗ trợ điều phối/recovery.

### 13.2. Batch ID và item key phục vụ mục đích khác nhau

- **Batch ID** nhận diện một đợt chạy, hữu ích để thống kê và khôi phục.
- **Item key** nhận diện một thao tác nghiệp vụ, phải ổn định qua các lần retry.
- **Input index** chỉ nhận diện vị trí trong mảng của một lần gọi.
- **MongoDB `_id`** nhận diện document ở collection, có thể tự sinh hoặc do ứng dụng cấp.
- **Payload digest** dùng để đối chiếu nội dung dưới cùng một item key.

Không lấy `batchId + vị trí index` làm khóa duy nhất nếu hệ thống nguồn có thể sắp xếp lại item hoặc chia lô khác vào lần chạy kế tiếp. Nếu một item chuyển từ batch A sang B thì danh tính nghiệp vụ của nó vẫn phải được nhận diện bằng external ID/operation ID ổn định.

### 13.3. Những chỉ số vận hành nên ghi nhận

| Chỉ số | Ý nghĩa |
| --- | --- |
| Tổng item đầu vào | Khối lượng mong đợi |
| Item được xác nhận | Tiến độ thực tế ở mức bảo đảm yêu cầu |
| Số item duplicate cùng payload | Tần suất yêu cầu lặp hợp lệ |
| Số item conflict khác payload | Nguy cơ lệch dữ liệu nguồn |
| Số item lỗi validation | Vấn đề schema hoặc parser |
| Số item unknown | Mức độ cần đối soát sau lỗi mạng/write concern |
| Số lần retry và độ trễ retry | Khả năng phục hồi, nguy cơ retry storm |
| Số document còn thiếu so với snapshot | Tính đầy đủ sau import/xóa |

Log hữu ích nên chứa `batchId`, `itemKey`, `attempt`, loại thao tác, mã lỗi, thời điểm và correlation ID. Không log token, mật khẩu, URI có credentials hoặc payload chứa dữ liệu cá nhân không cần thiết.

## 14. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi exception của bulk là cả lô rollback | Gửi lại các operation đã thành công | Đọc partial result, phân loại lỗi và đối soát |
| Coi `ordered: false` là luôn hoàn tất mọi operation | Có thể bỏ sót item khi lỗi toàn lệnh/mạng | Dùng checkpoint và xử lý trạng thái unknown |
| Coi operation không có `writeErrors` là chắc chắn đã commit majority | Nhầm mức bảo đảm khi có write concern error | Xử lý write concern và đọc lại với chính sách phù hợp |
| Retry `insertOne` với `_id` mới | Tạo duplicate nghiệp vụ | Dùng stable key, unique index hoặc upsert |
| Chỉ dùng `upsert: true` để ngăn trùng | Hai upsert đồng thời có thể tạo trùng nếu thiếu ràng buộc | Unique index đúng khóa |
| Bắt mọi `11000` và trả thành công | Che xung đột ở index khác hoặc payload khác | Tra cứu đúng key và so fingerprint |
| Retry `121` mãi | Không khắc phục document sai schema | Sửa parser/nguồn dữ liệu |
| Retry `$inc` sau timeout không đối soát | Tăng/trừ nhiều lần | Dùng operation ID và cơ chế idempotency |
| Dùng `deleteMany({})` để dọn sau bulk lỗi | Xóa vượt ngoài dữ liệu dự kiến | Snapshot ID, filter ownership rõ ràng |
| Tính lại cutoff khi retry dọn dữ liệu | Có thể xóa thêm document mới | Giữ cutoff của chiến dịch cố định |
| Dùng input index làm ID lâu dài | Retry qua batch mới bị ánh xạ sai | Lưu business key và batch ID riêng |
| Tin driver retry là đủ chống xử lý lặp | API/queue vẫn có thể phát lại cùng yêu cầu | Idempotency ở cấp nghiệp vụ |
| Bỏ qua state/version của bản ghi đang cập nhật | Có thể ghi đè trạng thái mới bằng event cũ | Conditional update, version/order policy |
| Gửi email ngay trong transaction callback | Retry callback có thể gửi lại email | Outbox và idempotent consumer |

## 15. Tình huống tổng hợp: nhập đơn hàng từ đối tác

Một hệ thống nhận 10.000 đơn hàng từ ERP mỗi giờ. Chọn thiết kế:

1. Chuẩn hóa `tenantId`, `sourceSystem`, `externalId` và nội dung nghiệp vụ.
2. Tạo unique index trên `{tenantId, sourceSystem, externalId}`. Bảo vệ cùng một đơn không xuất hiện hai lần trong collection.
3. Lưu `payloadDigest` và các trường chỉ khởi tạo trong `$setOnInsert`.
4. Tách lô theo kích thước hợp lý, dùng `ordered: false` khi mỗi đơn hàng độc lập.
5. Ghi nhận mapping index → item key của mỗi lô; đồng thời giữ snapshot dữ liệu nguồn.
6. Nếu gặp `11000`, đọc lại đúng key và so digest; cùng digest thì xem là đã tiếp nhận, khác digest thì đánh dấu conflict.
7. Nếu gặp `121`, đưa item vào hàng cần sửa dữ liệu, không retry vô hạn.
8. Nếu lỗi tạm thời, retry **chỉ item phù hợp**, với backoff và giới hạn số lần.
9. Nếu mất response hoặc có write concern error, đánh dấu unknown và đối soát theo mức nhất quán mong muốn trước khi xác nhận.
10. Dùng checkpoint bền vững để khôi phục sau khi worker chết, nhưng vẫn dựa vào unique key/idempotency để chống ghi lặp.

### Ví dụ kết quả vận hành

```text
Batch IMPORT-042 (5 items):

Item     Phản hồi ban đầu            Kết luận sau đối soát
----------------------------------------------------------------
O-101    Insert/upsert thành công     CONFIRMED
O-102    E11000                      CONFIRMED (cùng digest)
O-103    E11000                      CONFLICT (digest khác)
O-104    Validation 121              INVALID (sai amount type)
O-105    Không nhận được response    UNKNOWN -> đối soát/retry an toàn
```

Ở đây “O-102 đã tồn tại” là một kết luận **sau đối chiếu**, không đơn giản vì mã `11000`. O-103 không được âm thầm ghi đè. O-104 cần sửa dữ liệu nguồn. O-105 không được tự coi là thất bại rồi dùng thao tác có tác dụng tích lũy gửi lại.

Khi tất cả item cuối cùng được phân loại, hệ thống có thể báo số item đã hoàn thành, conflict, invalid và chưa rõ. Tổng số này phản ánh trạng thái nghiệp vụ chính xác hơn một cờ `success/failure` chung cho toàn batch.

## 16. Câu hỏi luyện tập

1. Với `ordered: true`, một lô gồm A, B, C có B báo duplicate key. A có thể đã thành công không? C đã được thực hiện chưa?
2. Với `ordered: false`, tại sao bulk ném lỗi vẫn có thể để lại nhiều document mới trong collection?
3. `matchedCount` và `modifiedCount` khác nhau như thế nào? Chúng có đủ để biết từng item đã xử lý không?
4. Tại sao cần phân biệt `writeErrors` với `writeConcernError`?
5. Nếu mất kết nối sau khi gửi bulk, có thể kết luận tất cả operation đều thất bại không?
6. Tại sao retry `$inc` có thể nguy hiểm dù filter luôn chứa một `_id` duy nhất?
7. Điều gì ngăn hai worker tạo hai đơn hàng có cùng `externalId` khi dùng upsert?
8. Khi gặp `E11000`, làm thế nào phân biệt “đã xử lý cùng request” với “xung đột hai payload khác nhau”?
9. Vì sao một `deleteOne` có `deletedCount: 0` sau retry không chứng minh document chưa từng được xóa?
10. Điểm khác nhau giữa batch ID, input index và business key trong hệ thống có retry là gì?
11. Khi nào có thể dùng unordered bulk với selective retry, khi nào phải cân nhắc transaction?
12. Vì sao chỉ thêm transaction vẫn chưa đủ để tránh một request thanh toán bị phát lại tạo side effect trùng?

## 17. Kết luận

Khi làm việc với **xóa và ghi theo lô** trong MongoDB, hãy thiết kế với giả định rằng **lỗi và phát lại yêu cầu đều có thể xảy ra**. `bulkWrite` giúp xử lý nhiều thao tác hiệu quả nhưng không tự bảo đảm toàn lô nguyên tử; `ordered` quyết định cách tiếp tục sau write error, còn response và error metadata cho biết một phần những gì đã diễn ra.

Để không mất dữ liệu hoặc ghi trùng, từng item phải có **khóa nghiệp vụ ổn định**, một thao tác ghi **có thể retry an toàn**, unique index bảo vệ ràng buộc và quy trình **đối soát trạng thái chưa rõ**. Chỉ gửi lại những item thực sự phù hợp để retry, đồng thời giữ checkpoint và theo dõi lỗi vĩnh viễn. Với các bất biến cần nhiều document cùng thành công, bổ sung transaction và cơ chế idempotency cấp nghiệp vụ thay vì dựa vào một lần gọi bulk duy nhất.
