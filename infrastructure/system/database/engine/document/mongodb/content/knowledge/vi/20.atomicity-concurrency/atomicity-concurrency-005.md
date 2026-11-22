# Unique index bảo vệ ràng buộc khi nhiều yêu cầu chạy đồng thời trong MongoDB

## 1. Vấn đề thực tế và mục tiêu

Một website cho phép tạo tài khoản bằng email, đặt chỗ trong một khung giờ hoặc đăng ký một mã giao dịch. Khi chỉ có một request, chương trình có thể đọc database, kiểm tra dữ liệu chưa tồn tại, rồi thêm mới. Nhưng trong hệ thống có nhiều người dùng, nhiều request có thể **đọc cùng lúc** và cùng kết luận rằng khóa đang rảnh.

Để bảo vệ quy tắc **“không được có hai document khác nhau cùng khóa nghiệp vụ”**, MongoDB cung cấp **unique index**. Ràng buộc này được thực thi ở tầng database khi dữ liệu được ghi, không phụ thuộc một ứng dụng, một process hoặc một pod backend.

Bài học thuộc chương **Nguyên tử và cạnh tranh** giải thích:

- Race condition **time-of-check to time-of-use (TOCTOU)** của mẫu `findOne()` rồi `insertOne()`.
- Tạo unique index một trường và compound unique index theo đúng phạm vi nghiệp vụ.
- Cách thao tác đồng thời bị chặn bằng duplicate key error `E11000`.
- Phân biệt tính nguyên tử của một document, unique index và transaction đa document.
- Upsert đồng thời, `$setOnInsert`, xử lý retry và idempotency key.
- Partial unique index cho bản ghi active, sparse/partial index, field null/missing, collation và multikey.
- Các giới hạn khi sharding, migration và kiểm thử nhiều writer.

**Nguyên tắc cốt lõi:** Kiểm tra ở tầng ứng dụng có thể giúp hiển thị thông báo sớm, nhưng **không thay thế unique index** nếu quy tắc duy nhất phải đúng dưới tải đồng thời.

## 2. Race condition: tại sao “kiểm tra rồi ghi” không an toàn?

Xét một endpoint tạo tài khoản:

~~~javascript
async function registerUser(users, emailKey) {
  const found = await users.findOne({ emailKey });

  if (found) {
    throw new Error("Email đã tồn tại");
  }

  return users.insertOne({
    emailKey,
    createdAt: new Date()
  });
}
~~~

Hai lệnh `findOne()` và `insertOne()` **không phải một thao tác nguyên tử duy nhất**. Chúng có thể bị xen kẽ với thao tác của client khác.

~~~text
Thời gian        Request A                       Request B
-----------------------------------------------------------------
T1               findOne(email = x)
T2               Không có document
T3                                               findOne(email = x)
T4                                               Không có document
T5               insertOne(email = x)
T6               Ghi thành công
T7                                               insertOne(email = x)
T8                                               Có thể cũng ghi
                                                 thành công nếu
                                                 không có unique index
-----------------------------------------------------------------
Kết quả: hai account có cùng email.
~~~

Ngay cả khi A và B cùng gọi `findOne()` ở bước T1–T4, database chưa có thông tin nào buộc lần ghi sau phải được xem là một ràng buộc chung. Đó là lỗi TOCTOU: dữ liệu **đúng khi kiểm tra** nhưng có thể **đã thay đổi khi sử dụng kết quả kiểm tra**.

Những biện pháp dưới đây **không đủ** khi hệ thống có nhiều writer:

- Thêm `sleep()` hoặc random delay.
- Kiểm tra lại bằng `countDocuments()` ngay trước khi insert.
- Khóa một nút ở frontend.
- Một mutex JavaScript chỉ tồn tại trong **một process** khi hệ thống có nhiều pod.
- Giả định request “không bao giờ trùng mili-giây”.
- Bật transaction rồi vẫn chỉ dựa vào việc đọc chưa thấy document.

MongoDB cần một cơ chế **đánh giá khóa trên đường ghi**, chứ không chỉ một truy vấn quan sát trạng thái trước đó.

## 3. Unique index làm gì tại thời điểm ghi?

Cú pháp cơ bản:

~~~javascript
db.users.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

MongoDB không cho hai document khác nhau trong phạm vi index lưu cùng giá trị `emailKey`. Nếu hai request gần như đồng thời insert cùng khóa, **không thể cả hai được chấp nhận với khóa trùng** khi unique index đã được xây thành công và đang được thực thi.

Một request có thể ghi được, còn request khác có thể nhận lỗi:

~~~text
E11000 duplicate key error ... index: ...
~~~

Mã lỗi phổ biến là **11000**. Trạng thái thành công hay thất bại cụ thể phụ thuộc thứ tự thực thi; không nên đoán trước request nào sẽ thắng.

So sánh:

| Tình huống | Không có unique index | Có unique index phù hợp |
| --- | --- | --- |
| Hai insert cùng khóa | Có thể cùng thành công | Chỉ tối đa một khóa trùng được chấp nhận |
| Hai upsert cùng khóa | Có thể tạo hai document | Không thể tạo hai document trùng; request có thể update hoặc lỗi |
| Update làm hai document có cùng email | Có thể làm dữ liệu trùng | Update vi phạm unique bị từ chối |
| Script import dữ liệu trùng | Có thể nhập trùng | Index chặn những document vi phạm |
| Hai service khác nhau cùng ghi | Logic ứng dụng có thể không đồng bộ | Ràng buộc vẫn nằm ở database |
| Find có sử dụng index hay không | Không ảnh hưởng khả năng chống trùng | Constraint unique vẫn được thực thi khi ghi |

**Index thường** với `{emailKey:1}` giúp tìm dữ liệu; chỉ khi có `unique: true` nó mới định nghĩa ràng buộc không trùng.

## 4. Chuẩn bị database thực hành và index đầu tiên

Mở `mongosh`; các lệnh sau chỉ dành cho database riêng. Không chạy `drop()` trên collection production.

~~~javascript
const lab = db.getSiblingDB("mongo_unique_concurrency_lab");

lab.accounts.drop();
lab.claims.drop();
lab.optionalCodes.drop();
lab.partialCodes.drop();
lab.reservations.drop();
lab.caseInsensitive.drop();
lab.aliases.drop();
lab.legacyUsers.drop();

lab.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  {
    unique: true,
    name: "uq_tenant_email"
  }
);

lab.accounts.getIndexes();
~~~

Định nghĩa trên bảo vệ **cặp khóa `(tenantId, emailKey)`**. Thêm account đầu:

~~~javascript
lab.accounts.insertOne({
  _id: "account-a",
  tenantId: "tenant-1",
  email: "An@Example.com",
  emailKey: "an@example.com",
  displayName: "An",
  createdAt: new Date()
});
~~~

Thử thêm cùng emailKey, cùng tenant, nhưng `_id` khác:

~~~javascript
try {
  lab.accounts.insertOne({
    _id: "account-b",
    tenantId: "tenant-1",
    email: "AN@example.com",
    emailKey: "an@example.com",
    displayName: "Another An",
    createdAt: new Date()
  });
} catch (err) {
  print("errorCode = " + err.code);
  print(err.message);
}
~~~

MongoDB trả lỗi duplicate key với `code: 11000`. `account-b` không được chèn.

Nhưng cùng email trong tenant khác vẫn hợp lệ:

~~~javascript
lab.accounts.insertOne({
  _id: "account-c",
  tenantId: "tenant-2",
  email: "an@example.com",
  emailKey: "an@example.com",
  displayName: "An from tenant 2",
  createdAt: new Date()
});

lab.accounts.find(
  { emailKey: "an@example.com" },
  { _id: 1, tenantId: 1, emailKey: 1 }
).sort({ tenantId: 1 });
~~~

Có hai tài khoản lưu thành công: một ở `tenant-1` và một ở `tenant-2`. Đây là **kết quả đúng** của compound unique index, không phải lỗi.

## 5. Mô phỏng hai writer cạnh tranh bằng mongosh

Tạo một unique key độc lập:

~~~javascript
lab.claims.createIndex(
  { claimKey: 1 },
  { unique: true, name: "uq_claim_key" }
);
~~~

Mở hai cửa sổ `mongosh` kết nối cùng database lab. Cả hai đọc:

~~~javascript
const lab = db.getSiblingDB("mongo_unique_concurrency_lab");

lab.claims.findOne({ claimKey: "seat-101" });
// null khi chưa có.
~~~

Giả sử cả hai cửa sổ đều thấy null. Tiếp theo:

**Session A:**

~~~javascript
lab.claims.insertOne({
  _id: "claim-A",
  claimKey: "seat-101",
  requestedBy: "A"
});
~~~

**Session B:**

~~~javascript
lab.claims.insertOne({
  _id: "claim-B",
  claimKey: "seat-101",
  requestedBy: "B"
});
~~~

Khi các insert có `_id` khác nhau nhưng `claimKey` giống nhau, **chỉ một insert có thể được chấp nhận** và thao tác còn lại nhận duplicate key. Không có bảo đảm A hay B sẽ thắng.

Kiểm tra:

~~~javascript
lab.claims.countDocuments({ claimKey: "seat-101" });
// 1 khi đã có một write thành công và vẫn tồn tại.
~~~

Thí nghiệm cho thấy **đọc null ở cả hai session không phải vấn đề** nếu mọi ghi đều đi qua constraint unique phù hợp.

### 5.1. Thử đồng thời bằng MongoDB Node.js Driver

Đoạn code này chạy trong ứng dụng Node.js, **không phải `mongosh`**. Cần package `mongodb` và URI kết nối hợp lệ:

~~~javascript
const { MongoClient } = require("mongodb");

async function main() {
  const client = new MongoClient(
    process.env.MONGODB_URI ?? "mongodb://127.0.0.1:27017"
  );

  try {
    await client.connect();

    const c = client
      .db("mongo_unique_concurrency_lab")
      .collection("concurrentTrials");

    // Chỉ xóa dữ liệu của thí nghiệm này.
    await c.deleteMany({ claimKey: "race-217" });

    await c.createIndex(
      { claimKey: 1 },
      { unique: true, name: "uq_trial_claim" }
    );

    const requests = Array.from(
      { length: 20 },
      (_, i) => c.insertOne({
        _id: "trial-" + i,
        claimKey: "race-217",
        requester: i
      })
    );

    const results = await Promise.allSettled(requests);

    const ok = results.filter(
      r => r.status === "fulfilled"
    ).length;

    const duplicates = results.filter(
      r => r.status === "rejected" && r.reason?.code === 11000
    ).length;

    const others = results.filter(
      r => r.status === "rejected" && r.reason?.code !== 11000
    ).length;

    console.log({
      ok,
      duplicates,
      others,
      stored: await c.countDocuments({ claimKey: "race-217" })
    });
  } finally {
    await client.close();
  }
}

main().catch(err => {
  console.error(err);
  process.exitCode = 1;
});
~~~

Khi thí nghiệm độc lập, index tồn tại và không có lỗi mạng/permission, kết quả dự kiến là:

~~~text
ok:         1
duplicates: 19
others:     0
stored:     1
~~~

Dùng `Promise.allSettled()` để thu thập **cả 20 kết quả**, không chỉ rejection đầu tiên như `Promise.all()` khi gặp lỗi. Vì các document có `_id` khác nhau, đây là thí nghiệm nhắm vào uniqueness của `claimKey`. Chạy đồng thời nhiều bản sao của **chính bài test** có thể gây thêm va chạm `_id` và làm số liệu khó diễn giải; nên cô lập mỗi test run.

## 6. Unique index áp dụng lên những thao tác nào?

Ràng buộc unique không chỉ được kiểm tra khi `insertOne()`:

| Thao tác | Điều được kiểm tra |
| --- | --- |
| `insertOne()` | Document mới có tạo index key trùng không? |
| `insertMany()` / `bulkWrite()` | Mỗi write có vi phạm index không? |
| `updateOne()` | Giá trị key mới có đụng document khác không? |
| `updateMany()` | Những document được cập nhật có còn đáp ứng unique không? |
| `replaceOne()` | Document thay thế có tạo khóa trùng không? |
| `findOneAndUpdate()` | Cập nhật/upsert có vi phạm constraint không? |
| `updateOne(..., {upsert:true})` | Document vừa insert hoặc update có làm trùng key không? |
| Ghi trong transaction | Constraint vẫn được xét; transaction không cho phép bỏ qua unique index |

Thử update `account-c` thuộc tenant-2 sang tenant-1 nhưng giữ emailKey:

~~~javascript
try {
  lab.accounts.updateOne(
    { _id: "account-c" },
    { $set: { tenantId: "tenant-1" } }
  );
} catch (err) {
  print(err.code); // 11000.
}
~~~

Kết quả update không được chấp nhận vì sau khi đổi tenant, cặp khóa sẽ trùng `account-a`.

**Tính nguyên tử cấp document** bảo đảm thay đổi đối với một document được thực hiện như một thao tác nguyên tử; nó **không tự đảm bảo bất biến liên quan đến hai document khác nhau**. Unique index là phần bổ sung để kiểm tra ràng buộc **giữa các document**.

## 7. E11000: nhận biết và phản hồi đúng

Thông báo lỗi thường có dạng:

~~~text
E11000 duplicate key error collection: ...
index: uq_tenant_email dup key: ...
~~~

Đây là dạng minh họa; format thay đổi theo driver/server/index.

Cần phân biệt:

1. `code: 11000` thường dùng để nhận diện duplicate key error.
2. Lỗi có thể đến từ **unique index nào đó**, bao gồm `_id_`, không nhất thiết từ index email.
3. Một số driver cung cấp `keyPattern`, `keyValue` hoặc tên index, nhưng không nên yêu cầu mọi môi trường đều có cùng cấu trúc thông tin.
4. `E11000` không phải lỗi cần retry liên tục bằng cùng dữ liệu nếu khóa vẫn xung đột.
5. `E11000` **không chứng minh** request nghiệp vụ trước đã thành công hoàn toàn.

### 7.1. Catch lỗi bằng code

~~~javascript
try {
  lab.accounts.insertOne({
    _id: "another-account",
    tenantId: "tenant-1",
    emailKey: "an@example.com"
  });
} catch (err) {
  if (err.code === 11000) {
    print("Xung đột khóa duy nhất");
  } else {
    throw err; // Không che lỗi mạng/validation/authorization.
  }
}
~~~

**Không gửi nguyên văn raw error hoặc stack trace** cho API client vì có thể lộ tên collection, index, khóa cá nhân hoặc chi tiết triển khai.

### 7.2. REST API tạo mới thường trả 409

~~~javascript
async function createAccount(accounts, request) {
  const emailKey = request.email.trim().toLowerCase();

  try {
    const result = await accounts.insertOne({
      tenantId: request.tenantId,
      email: request.email,
      emailKey,
      displayName: request.displayName,
      createdAt: new Date()
    });

    return {
      status: 201,
      body: { id: String(result.insertedId) }
    };
  } catch (err) {
    if (err?.code === 11000) {
      return {
        status: 409,
        body: { code: "ACCOUNT_ALREADY_EXISTS" }
      };
    }
    throw err;
  }
}
~~~

Trong API production, cần xác định **index nào gây xung đột** nếu collection có nhiều unique indexes. Mẫu trên minh họa response nghiệp vụ ngắn gọn, không phải middleware đã phân loại đầy đủ mọi loại duplicate.

### 7.3. Đừng tự coi E11000 là thành công idempotent

Nếu request mới dùng cùng khóa nhưng **payload khác**, `E11000` không có nghĩa người gọi đã nhận cùng kết quả. Đặc biệt với thanh toán, booking và order, cần kiểm tra khóa, nội dung yêu cầu, trạng thái đã lưu và quy tắc retry/idempotency trước khi trả response.

## 8. Compound unique index: xác định chính xác phạm vi

Index một trường:

~~~javascript
db.users.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

Ràng buộc emailKey duy nhất trong collection.

Index nhiều trường:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

Ràng buộc **cặp** duy nhất.

| tenantId | emailKey | Kết quả với compound unique |
| --- | --- | --- |
| t1 | an@example.com | Hợp lệ nếu chưa có |
| t1 | an@example.com | **Bị từ chối** nếu cặp đã tồn tại |
| t2 | an@example.com | Hợp lệ vì tenant khác |
| t1 | binh@example.com | Hợp lệ vì email khác |

Một index ba trường như:

~~~javascript
db.inventory.createIndex(
  { tenantId: 1, warehouseId: 1, serialKey: 1 },
  { unique: true }
);
~~~

chỉ bảo vệ **bộ ba**. Nó không nói serialKey duy nhất trên tất cả kho.

Các câu hỏi quan trọng trước khi chọn index:

- User đăng ký email duy nhất **trên toàn ứng dụng** hay **trong tenant**?
- Một mã đơn là duy nhất **trong shop** hay **trên toàn nền tảng**?
- Một ghế được giữ **trong từng show** hay bất kể show?
- Bản ghi đã hủy hoặc soft-delete có cần giữ vị trí trong unique index không?
- Các field hợp thành khóa có luôn tồn tại và đúng BSON type không?

Compound index cũng có thể hỗ trợ query filter phù hợp, nhưng **hiệu năng query** và **unique constraint khi ghi** là hai khía cạnh riêng.

## 9. Chuẩn hóa khóa và collation

### 9.1. Unique index không tự hiểu quy tắc email của ứng dụng

Nếu index dùng simple collation, hai chuỗi sau có thể là **hai key khác nhau**:

~~~text
An@Example.com
an@example.com
~~~

Nếu ứng dụng muốn xem chúng là một email logic, cần định nghĩa sự tương đương trước khi tạo index.

### 9.2. Lưu một field chuẩn hóa

Thiết kế gợi ý:

~~~javascript
{
  email: "An@Example.com",
  emailKey: "an@example.com"
}
~~~

Tất cả write paths phải dùng cùng quy tắc tạo `emailKey`. Có thể minh họa bằng `trim().toLowerCase()` đối với dữ liệu email thông thường, nhưng với email quốc tế hóa, phải có chính sách đầy đủ. Không tự loại dấu chấm hoặc phần sau ký tự `+` theo quy tắc của một provider rồi áp dụng cho mọi địa chỉ email.

Index trên `emailKey`:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

### 9.3. Dùng unique index có collation

Nếu muốn giữ nguyên chuỗi và so sánh **không phân biệt hoa/thường**:

~~~javascript
lab.caseInsensitive.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uq_email_case_insensitive",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);

lab.caseInsensitive.insertOne({
  _id: 1,
  email: "An@Example.com"
});

try {
  lab.caseInsensitive.insertOne({
    _id: 2,
    email: "an@example.com"
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

Với collation được chọn, chuỗi khác case có thể được so sánh tương đương. Muốn query dùng index collation này phù hợp, cần dùng collation tương thích:

~~~javascript
lab.caseInsensitive.find({
  email: "AN@example.com"
}).collation({
  locale: "en",
  strength: 2
});
~~~

Việc unique index có collation **không** có nghĩa mọi truy vấn không chỉ định collation đều tự khớp theo quy tắc đó nếu collection không được cấu hình mặc định cùng collation. Với sharded collection, unique index còn có hạn chế collation riêng.

## 10. Null và field thiếu trong unique index

MongoDB tạo index key cho giá trị `null` và field **không tồn tại** theo quy tắc riêng. Với unique index **single-field**, MongoDB chỉ cho phép **một document** có entry null (bao gồm trường thiếu hoặc null).

~~~javascript
lab.optionalCodes.createIndex(
  { externalCode: 1 },
  { unique: true, name: "uq_external_code" }
);

lab.optionalCodes.insertOne({
  _id: "missing-first"
});

try {
  lab.optionalCodes.insertOne({
    _id: "explicit-null",
    externalCode: null
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

Document thứ hai có thể bị xem là trùng index key null với document thứ nhất.

Với compound unique index `{tenantId:1,emailKey:1}`:

~~~javascript
{ tenantId: "t1" } // indexed combination ("t1", null)
{ tenantId: "t2" } // indexed combination ("t2", null)
~~~

Hai cặp **khác nhau** có thể cùng tồn tại. Nhưng hai document thiếu emailKey **trong cùng tenant** có thể sinh cùng compound key và vi phạm constraint.

**Đừng suy luận** rằng “compound unique luôn cho nhiều missing” hoặc “missing luôn khác null”. Ràng buộc dựa trên **toàn bộ tổ hợp indexed keys**.

### 10.1. Field bắt buộc cần validation

Nếu `tenantId` và `emailKey` là bắt buộc, unique index **không đủ** để kiểm tra format/kiểu:

~~~javascript
lab.runCommand({
  collMod: "accounts",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "emailKey"],
      properties: {
        tenantId: { bsonType: "string", minLength: 1 },
        emailKey: { bsonType: "string", minLength: 1 }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Đây là ví dụ bổ sung cho lab. Với collection thật, cần xem validator đã có và dữ liệu cũ trước khi gọi `collMod`, tránh ghi đè schema hiện hành một cách vô ý.

## 11. Sparse unique và partial unique cho field tùy chọn

### 11.1. Sparse unique

~~~javascript
db.users.createIndex(
  { externalCode: 1 },
  {
    unique: true,
    sparse: true
  }
);
~~~

Với index sparse một trường:

- Document **thiếu** `externalCode` không được index.
- Nhiều document thiếu field có thể cùng tồn tại.
- Document **có field với giá trị null** vẫn được index.
- Hai document có cùng giá trị string vẫn bị chặn.

Vì thế sparse **không đồng nghĩa** “bỏ qua null”.

### 11.2. Partial unique trên các string

~~~javascript
lab.partialCodes.createIndex(
  { externalCode: 1 },
  {
    unique: true,
    name: "uq_external_string",
    partialFilterExpression: {
      externalCode: { $type: "string" }
    }
  }
);

lab.partialCodes.insertMany([
  { _id: "a" },
  { _id: "b", externalCode: null },
  { _id: "c", externalCode: null }
]);

lab.partialCodes.insertOne({
  _id: "d",
  externalCode: "CODE-01"
});

try {
  lab.partialCodes.insertOne({
    _id: "e",
    externalCode: "CODE-01"
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

Partial unique constraint chỉ áp dụng cho document thỏa `partialFilterExpression`. Trong ví dụ, giá trị missing/null không thuộc tập được index; hai chuỗi `"CODE-01"` thì cạnh tranh cùng unique key.

**Lưu ý:** chuỗi rỗng `""` vẫn có kiểu string; nếu nghiệp vụ không cho giá trị rỗng, cần kiểm tra/validation. Partial unique index chỉ bảo vệ phần dữ liệu mà filter của nó chọn.

## 12. Partial unique index cho booking active và soft delete

Một hệ thống đặt phòng muốn:

- Không có hai booking **active** cho cùng phòng, cùng mốc giờ.
- Giữ lịch sử booking đã hủy.
- Cho đặt lại slot sau khi booking cũ không còn active.

Unique index vô điều kiện trên `(roomId, startAt)` sẽ giữ khóa của cả booking đã hủy. Dùng **partial unique index**:

~~~javascript
lab.reservations.createIndex(
  { roomId: 1, startAt: 1 },
  {
    unique: true,
    name: "uq_active_room_start",
    partialFilterExpression: { active: true }
  }
);
~~~

Chèn booking đầu:

~~~javascript
const slot = ISODate("2026-11-16T09:00:00Z");

lab.reservations.insertOne({
  _id: "booking-A",
  roomId: "R-01",
  startAt: slot,
  active: true,
  reservedBy: "An"
});
~~~

Booking thứ hai **active** cùng slot bị chặn:

~~~javascript
try {
  lab.reservations.insertOne({
    _id: "booking-B",
    roomId: "R-01",
    startAt: slot,
    active: true,
    reservedBy: "Binh"
  });
} catch (err) {
  print(err.code); // 11000.
}
~~~

Booking đã hủy có thể giữ làm lịch sử:

~~~javascript
lab.reservations.insertOne({
  _id: "booking-C",
  roomId: "R-01",
  startAt: slot,
  active: false,
  reservedBy: "Chi",
  cancelledAt: new Date()
});
~~~

Nếu cố đổi `booking-C` thành active khi `booking-A` còn active:

~~~javascript
try {
  lab.reservations.updateOne(
    { _id: "booking-C" },
    { $set: { active: true } }
  );
} catch (err) {
  print(err.code); // 11000.
}
~~~

**Update làm document đi vào tập partial index cũng bị kiểm tra uniqueness.**

Nếu hủy booking A:

~~~javascript
lab.reservations.updateOne(
  { _id: "booking-A", active: true },
  { $set: { active: false, cancelledAt: new Date() } }
);
~~~

thì một booking active mới cùng room/start có thể được thêm, nếu không có writer khác chiếm slot trước.

### 12.1. Giới hạn của partial unique

- Writer quên `active` hoặc ghi `active: "true"` thay vì boolean có thể **nằm ngoài filter**, trừ khi schema validation chặn.
- Nếu có trạng thái `pending`, `confirmed` và `cancelled`, cần định nghĩa rõ trạng thái nào chiếm chỗ.
- Partial unique index chỉ chặn **khóa giống nhau**, không chặn **hai khoảng thời gian giao nhau**.

Ví dụ cuộc hẹn `09:00–10:00` và `09:30–10:30` có `startAt` khác nhau. Unique trên `(roomId,startAt)` **không bảo vệ quy tắc không overlap**. Cần mô hình slot rời rạc hoặc cơ chế đặt chỗ có coordination/transaction phù hợp.

### 12.2. Hủy và cấp lại chỗ là quy trình nhiều bước

Index giữ bất biến “tối đa một booking active cho mỗi slot”, nhưng **không đảm bảo** rằng các thao tác hủy, ghi thanh toán, cập nhật lịch và gửi thông báo đều thành công như một transaction. Cần tách **ràng buộc khóa** khỏi **quy trình nghiệp vụ**.

## 13. Multikey unique index: bảo vệ giữa các document, không phải trong một mảng

Index trên field dạng array tạo **multikey index**. Nếu có `unique: true`, MongoDB chặn các document **khác nhau** tạo index key trùng. Nhưng một document có thể có phần tử lặp **ngay trong mảng của nó**.

~~~javascript
lab.aliases.createIndex(
  { aliases: 1 },
  { unique: true, name: "uq_aliases" }
);

lab.aliases.insertOne({
  _id: "doc-A",
  aliases: ["alpha", "alpha", "beta"]
});
~~~

Mảng có `"alpha"` lặp nhưng unique multikey không tự xem đây là vi phạm giữa hai document.

~~~javascript
try {
  lab.aliases.insertOne({
    _id: "doc-B",
    aliases: ["beta", "gamma"]
  });
} catch (err) {
  print(err.code); // 11000: beta ở doc-A.
}
~~~

Muốn **các phần tử trong cùng mảng không được trùng**, cần validation hoặc logic khác, ví dụ JSON Schema với `uniqueItems: true`:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    properties: {
      aliases: {
        bsonType: "array",
        items: { bsonType: "string" },
        uniqueItems: true
      }
    }
  }
}
~~~

`$addToSet` cũng phục vụ một số cập nhật mảng không thêm trùng, nhưng nó không thay unique index giữa các document và không tự sửa mảng đã có dữ liệu trùng.

Với **compound multikey**, có thêm giới hạn về nhiều field mảng trong cùng một document; không thể tùy ý ghép nhiều mảng vào index rồi kỳ vọng MongoDB bảo vệ mọi tổ hợp.

## 14. Upsert đồng thời: có index nhưng vẫn cần xử lý lỗi

`upsert: true` có nghĩa: nếu filter khớp document, cập nhật; nếu chưa khớp, thử tạo document mới.

~~~javascript
const result = lab.accounts.updateOne(
  {
    tenantId: "tenant-1",
    emailKey: "binh@example.com"
  },
  {
    $setOnInsert: {
      email: "Binh@Example.com",
      displayName: "Binh",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(result);
~~~

### 14.1. Không có unique index

Hai upsert có thể cùng hoàn thành bước tìm kiếm khi chưa có document, sau đó đều insert. `upsert: true` **không tự đảm bảo khóa duy nhất**.

### 14.2. Có unique index phù hợp

Với index `{tenantId:1,emailKey:1}, unique: true`, **hai document trùng không thể cùng được chấp nhận**. Trong cạnh tranh, thao tác khác có thể:

- Update document vừa được một request insert.
- Nhận `E11000`.
- Nhận lỗi khác liên quan điều kiện mạng/transaction.

MongoDB mô tả những điều kiện để upsert cạnh tranh có thể cập nhật document vừa insert: filter là một hoặc nhiều **equality predicates**, các field của filter khớp với key pattern của unique index, thao tác không phải multi-update và update không thay đổi field tạo khóa unique.

**Không hứa mọi upsert đồng thời đều thành công**. Khi có thêm điều kiện trạng thái trong filter, khả năng update document vừa insert có thể không còn áp dụng.

### 14.3. Ví dụ filter dễ gây duplicate

~~~javascript
lab.accounts.updateOne(
  {
    tenantId: "tenant-1",
    emailKey: "binh@example.com",
    status: "pending"
  },
  {
    $setOnInsert: {
      displayName: "Binh",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Nếu document cùng tenant/email **đã tồn tại nhưng status khác pending**, filter không khớp, upsert có thể cố insert document mới cùng unique key và bị `E11000`.

Thiết kế tốt là phân biệt:

1. **Khóa định danh** được unique index bảo vệ.
2. **Điều kiện chuyển trạng thái** để update document cụ thể.
3. **Chính sách** khi document đã tồn tại nhưng không ở trạng thái mong đợi.

### 14.4. Đọc kết quả upsert

Các trường thường gặp:

| Trường | Ý nghĩa |
| --- | --- |
| `matchedCount` | Số document khớp để update |
| `modifiedCount` | Số document đã thay đổi dữ liệu |
| `upsertedId` | Định danh của document mới được insert |
| `acknowledged` | Kết quả có được xác nhận theo write concern không |

`modifiedCount: 0` không đồng nghĩa “không có document”: có thể đã match nhưng update không làm thay đổi giá trị. Trong ứng dụng, dùng kết quả theo đúng ý nghĩa của API driver.

## 15. Unique index và idempotency key

Hệ thống thường nhận lại **cùng một request** do mạng lỗi, gateway retry, người dùng bấm hai lần hoặc queue gửi lại message. Đối với thanh toán và tạo đơn, yêu cầu không chỉ là “không trùng email”, mà còn là **một idempotency key không được khởi tạo hai workflow độc lập**.

### 15.1. Tạo unique claim

~~~javascript
lab.idempotencyClaims.drop();

lab.idempotencyClaims.createIndex(
  { tenantId: 1, operationKey: 1 },
  {
    unique: true,
    name: "uq_tenant_operation"
  }
);
~~~

Khi nhận request:

~~~javascript
lab.idempotencyClaims.insertOne({
  tenantId: "tenant-1",
  operationKey: "checkout-001",
  payloadHash: "canonical-request-hash",
  state: "processing",
  createdAt: new Date()
});
~~~

Nếu hai worker cùng insert `(tenant-1,checkout-001)`, unique index đảm bảo không có hai claim trùng khóa được chấp nhận.

### 15.2. Cách xử lý khi claim đã tồn tại

~~~text
Nhận request (tenantId, operationKey, payload)
           |
           v
Tính payloadHash từ yêu cầu đã chuẩn hóa
           |
           v
Thử INSERT claim với unique key
           |
           +-- Insert thành công
           |     -> bắt đầu xử lý nghiệp vụ
           |     -> lưu trạng thái/kết quả phục hồi được
           |
           +-- E11000
                 -> đọc claim đã lưu
                 |
                 +-- payloadHash khác
                 |     -> 409: cùng key nhưng khác yêu cầu
                 |
                 +-- payloadHash giống, completed
                 |     -> trả lại kết quả đã ghi (theo contract)
                 |
                 +-- payloadHash giống, processing
                       -> báo đang xử lý/chờ hoặc retry có giới hạn
~~~

**Không coi `E11000` là bằng chứng rằng thanh toán đã hoàn tất**. Có thể request trước mới chỉ tạo claim, chưa gọi payment provider, hoặc đang phục hồi sau crash.

### 15.3. Idempotency không đồng nghĩa exactly-once cho hệ thống ngoài

Giả sử quy trình:

1. Insert claim trong MongoDB.
2. Gửi lệnh thu tiền tới payment provider.
3. Update claim thành `completed`.

Nếu process chết giữa bước 2 và 3, claim vẫn có thể ở `processing` dù nhà cung cấp đã thu tiền. Unique index ngăn tạo **claim trùng**, nhưng không biến bước 2 (một hệ thống khác) thành transaction nguyên tử với MongoDB.

Cần kết hợp idempotency key ở payment provider, outbox/inbox, đối soát, trạng thái có thể phục hồi, timeout và retry được thiết kế cẩn thận. Đừng xóa claim quá sớm: một request cũ gửi lại sau khi claim bị xóa sẽ có thể được xem là request mới.

TTL có thể phục vụ retention theo hợp đồng, nhưng việc xóa TTL chạy bất đồng bộ; nó không phải cách nhả “khóa giao dịch” chính xác đến từng mili-giây.

## 16. Unique index, atomicity và transaction là các lớp khác nhau

MongoDB có tính nguyên tử ở cấp **một document** đối với thao tác ghi. Nhưng một quy tắc như “hai document không cùng mã” là **ràng buộc xuyên nhiều document**. Unique index giải quyết ràng buộc đó bằng khóa index.

| Cơ chế | Bảo đảm chính | Không tự bảo đảm |
| --- | --- | --- |
| Atomic single-document update | Không có trạng thái cập nhật dở của một document | Unique giữa nhiều document nếu không index |
| Unique index | Không trùng key trong phạm vi index | Tất cả business invariants, multi-doc transaction |
| Transaction đa document | Atomicity của nhóm thao tác được commit | Khóa nào nghiệp vụ coi là trùng nếu không định nghĩa |
| Pre-check ứng dụng | UX/validation sớm | Không race khi request chạy đồng thời |
| Write concern | Mức xác nhận ghi/replication | Không tạo constraint unique |
| Retryable writes | Hỗ trợ retry theo driver/server | Không chứng minh side effect ngoài DB exactly-once |

### 16.1. Transaction không thay unique index

Hai transaction có thể cùng đọc thấy “chưa có tài khoản email x”. Tính chất transaction/đọc snapshot **không nên được dùng như thay thế** ràng buộc unique. Khi cả hai cố ghi cùng unique key, có thể phát sinh duplicate key hoặc write conflict/transaction error tùy tình huống và thứ tự thực thi. Ứng dụng phải xử lý lỗi và abort/retry khi phù hợp.

### 16.2. Khi nào cần transaction thêm?

Ví dụ đặt ghế cần:

- Insert reservation vào `reservations`.
- Trừ số ghế trống trong `events`.
- Ghi payment record vào `payments`.

Unique index trên `(showId,seatCode)` chặn hai reservation cùng ghế, nhưng không đảm bảo **cả ba write ở ba document/collection** cùng commit hay rollback. Nếu nghiệp vụ yêu cầu all-or-nothing, cần transaction đa document trên topology hỗ trợ, cùng chi phí/giới hạn và cơ chế retry hợp lệ.

### 16.3. Các ràng buộc mà unique index không giải quyết

| Nghiệp vụ | Unique index đủ không? | Cơ chế cần cân nhắc |
| --- | --- | --- |
| Một email trong tenant | Có, khi key đúng | Validation/chuẩn hóa |
| Một ghế trong show | Có, theo khóa và điều kiện active | Trạng thái/audit |
| Tồn kho không được âm | Không | Conditional atomic update |
| Tổng số đặt chỗ không vượt capacity | Không tự đủ | Counter/conditional write/transaction |
| Hai booking bất kỳ không overlap | Không chỉ bằng startAt | Slot model/serialization |
| Chuyển tiền giữa hai ví all-or-nothing | Không | Transaction |
| Webhook chỉ có một claim mỗi key | Có ở bước claim | Idempotency workflow đầy đủ |

Ví dụ trừ tồn kho đúng loại atomic update trên **một** document:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-101", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
);
~~~

Điều kiện `stock >= 2` được gắn với thao tác ghi, tránh mẫu đọc stock rồi ghi đè không điều kiện. Đây là **bài toán khác** với duplicate key, nhưng cùng nằm trong chủ đề cạnh tranh.

## 17. Bulk writes và updateMany không tự có atomicity toàn bộ

Với `insertMany()` có index unique:

~~~javascript
// Minh họa nghiệp vụ: có thể có lỗi duplicate từng item.
db.users.insertMany(
  [
    { tenantId: "t1", emailKey: "a@example.com" },
    { tenantId: "t1", emailKey: "a@example.com" },
    { tenantId: "t1", emailKey: "b@example.com" }
  ],
  { ordered: false }
);
~~~

- `ordered: true` thường dừng xử lý những write tiếp theo sau lỗi đầu theo thứ tự.
- `ordered: false` có thể tiếp tục những item khác và báo danh sách lỗi.
- Không mặc định cả batch rollback khi có một document trùng.

Với `updateMany()`:

~~~javascript
// ĐỪNG CHẠY trên dữ liệu cần giữ.
// Có thể làm một vài document đổi key trước khi gặp duplicate.
db.users.updateMany(
  { tenantId: "t1" },
  { $set: { emailKey: "shared@example.com" } }
);
~~~

Mỗi document cập nhật vẫn phải tuân thủ unique constraint, nhưng `updateMany` **không mặc định là một transaction nguyên tử trên toàn bộ các document**. Nếu cập nhật một document trước khi document kế tiếp gặp duplicate, có thể đã có thay đổi được ghi.

Khi cần tất cả cùng thành công hoặc thất bại, thiết kế transaction/migration riêng. Không suy luận rằng một lỗi `E11000` đảm bảo mọi thao tác trong bulk chưa thay đổi dữ liệu.

## 18. Replica set, failover, write concern và retry

### 18.1. Write concern không phải uniqueness

Trên replica set, `w: "majority"` có thể dùng để yêu cầu xác nhận ghi qua đa số member theo quy tắc triển khai:

~~~javascript
lab.accounts.insertOne(
  {
    tenantId: "tenant-1",
    emailKey: "majority@example.com",
    displayName: "Majority Test"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

Lệnh này chỉ minh họa mức xác nhận ghi; nó **không thay unique index**. Nếu `emailKey` trùng, dù dùng majority hay không, constraint vẫn cần được thực thi.

### 18.2. Timeout có thể làm client không biết trạng thái write

~~~text
Client gửi insert
       |
       v
Server thực hiện write
       |
       v
Network timeout trước khi acknowledgment về tới client
       |
       v
Client không chắc thao tác đã được ghi hay chưa
~~~

Nếu ứng dụng tự gửi lại cùng request:

- Nếu document trước đã tồn tại, retry có thể gặp `E11000`.
- Nếu write trước chưa được thực hiện hoặc bị rollback theo tình huống failover, retry có thể tạo mới.
- Nếu dùng **retryable writes** của driver, có cơ chế và điều kiện riêng. Không đánh đồng cơ chế driver với việc gọi lại nghiệp vụ một cách tùy ý.

Không xem `E11000` sau timeout là bằng chứng **mọi side effect đã hoàn tất**; dùng idempotency key, đọc trạng thái và đối soát.

### 18.3. Xây unique index trên replica set

Index build có quy tắc đồng bộ/commit quorum. Với một số rolling procedures tạo **unique index**, MongoDB yêu cầu ngừng ghi vào collection trong quá trình thực hiện. Nếu không thể ngừng ghi, cần dùng phương thức index build được hỗ trợ qua primary (replica set) hoặc `mongos` (sharded cluster) theo tài liệu version.

Không kiểm tra một node có index rồi kết luận **toàn topology** đang bảo vệ uniqueness như mong muốn.

## 19. Sharded cluster: uniqueness gắn với shard key

Trên sharded collection, MongoDB có quy tắc hạn chế unique indexes để đảm bảo constraint có thể được thực thi giữa các shard.

Với **ranged sharding**, unique index phải là index của shard key hoặc có **toàn bộ shard key làm prefix**. Ví dụ collection sharded theo:

~~~javascript
{ tenantId: 1 }
~~~

Index hợp lệ cho tính duy nhất của email trong tenant:

~~~javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

Ngược lại:

~~~javascript
// Không có shard-key prefix, không phù hợp với
// collection sharded theo { tenantId: 1 }.
db.accounts.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

Một email có thể xuất hiện trong nhiều tenant. Nếu cần email **duy nhất toàn platform** dù có nhiều shard, phải thiết kế shard key hoặc registry/collection global unique khác phù hợp. Không đơn giản bỏ `tenantId` khỏi index rồi kỳ vọng sharded cluster sẽ cho phép.

### 19.1. _id không luôn có uniqueness toàn cluster

Với sharded collection mà `_id` không phải shard key, unique constraint của `_id` có thể chỉ được thực thi trên từng shard. Ứng dụng phải bảo đảm định danh đủ duy nhất toàn cluster trong tình huống đó.

### 19.2. Hashed index không unique

~~~javascript
// Không hợp lệ: hashed index không hỗ trợ unique.
db.accounts.createIndex(
  { tenantId: "hashed" },
  { unique: true }
);
~~~

Nếu sharding theo hashed key, cần xem quy tắc unique index cho topology cụ thể, không cố thêm `unique` vào hashed index.

### 19.3. Collation trong sharded uniqueness

Sharded uniqueness còn có giới hạn về collation; MongoDB chỉ đảm bảo uniqueness theo quy tắc được hỗ trợ, đặc biệt với **simple collation**. Với email không phân biệt hoa/thường, cách tương đối dễ kiểm soát là lưu `emailKey` chuẩn hóa rồi dùng index unique có shard-key prefix và giá trị so sánh simple, thay vì suy luận một collated unique index bất kỳ sẽ hoạt động global.

## 20. Triển khai unique index lên collection đã có dữ liệu

Không thể xây unique index thành công nếu collection **đang có những document trùng index key**. Đây là một bài toán migration, không chỉ là chạy một lệnh DDL.

### 20.1. Tìm trùng trước khi tạo index

~~~javascript
db.accounts.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        emailKey: "$emailKey"
      },
      count: { $sum: 1 },
      exampleId: { $first: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 20 }
]);
~~~

Pipeline này nhóm theo **đúng compound key** định dùng unique. Nếu chưa có field chuẩn hóa, hai email khác case sẽ không tự trở thành cùng giá trị. Cần thống nhất policy và backfill trước.

Không mặc định dùng `$push: "$_id"` để giữ **mọi ID** của nhóm trùng trên collection rất lớn: mảng có thể quá lớn và gây lỗi memory/BSON. Lúc đầu chỉ cần count và ID đại diện để khoanh vùng.

### 20.2. Kế hoạch rollout có kiểm soát

1. Xác định uniqueness toàn cục, theo tenant hay theo trạng thái active.
2. Chuẩn hóa key, kiểm tra kiểu BSON, xử lý null/missing.
3. Dò và giải quyết duplicate lịch sử theo chính sách merge/retire/audit.
4. Đảm bảo **không có writer tiếp tục tạo duplicate** trong khoảng chuyển đổi. Có thể cần tạm ngừng ghi liên quan hoặc chuyển lưu lượng theo quy trình riêng.
5. Tạo index unique bằng lệnh/quy trình phù hợp topology và đợi build thành công.
6. Kiểm tra `getIndexes()`, build status và thử những thao tác gây trùng trong môi trường test.
7. Bổ sung schema validation nếu field khóa phải luôn có mặt.
8. Cập nhật mọi service, background job, import script để tạo khóa chuẩn hóa giống nhau.
9. Theo dõi `E11000`, write latency, index size và các lỗi phát sinh sau rollout.

**Race ở giai đoạn triển khai:** Kiểm tra duplicate lúc 10:00 rồi tạo index lúc 10:05 không đủ nếu trong năm phút đó writer vẫn có thể thêm dữ liệu trùng. Unique index chưa build thành công thì constraint chưa thể được xem là bảo vệ đầy đủ.

### 20.3. Không tự đổi một index thường thành unique

Nếu một compound index không unique đã tồn tại, việc gọi `createIndex()` một lần nữa với options khác **không nên được coi là cách đổi nó thành unique trong mọi phiên bản**. MongoDB có quy trình riêng để chuyển index hiện có sang unique hoặc tạo index phù hợp sau khi giải quyết duplicate.

Đặc biệt **không drop unique index đang bảo vệ rule trong lúc hệ thống tiếp tục ghi** mà chưa có cơ chế thay thế. Kết quả có thể là cửa sổ cho phép dữ liệu trùng.

## 21. Hiệu năng, vận hành và theo dõi

Unique index làm tăng chi phí duy trì mỗi khi insert/update/delete thay đổi key: thêm index entries, sử dụng đĩa/cache và xử lý index build. Nhưng nếu uniqueness là bất biến bắt buộc, không nên bỏ ràng buộc chỉ để tăng throughput.

Một compound unique index còn có thể giúp tìm nhanh:

~~~javascript
lab.accounts.find({
  tenantId: "tenant-1",
  emailKey: "an@example.com"
}).explain("executionStats");
~~~

Tuy nhiên **query planner có dùng `IXSCAN` hay không không quyết định việc MongoDB có thực thi unique constraint khi ghi**. `explain()` kiểm tra đường đọc; còn index definition và bài test ghi trùng xác nhận ràng buộc.

Kiểm tra metadata:

~~~javascript
lab.accounts.getIndexes().filter(
  idx => idx.name === "uq_tenant_email"
);
~~~

Các chỉ số nên quan sát trong hệ thống thật:

- Số lỗi `E11000` theo index/operation/tenant (ẩn dữ liệu nhạy cảm).
- Tỷ lệ retry sau timeout.
- Số request mang cùng idempotency key.
- Thời gian index build, chi phí ghi và index storage.
- Mức độ trùng khóa trong dữ liệu import/batch.
- Lỗi `E11000` bất ngờ do null/missing hoặc service chuẩn hóa khác nhau.

Một lượng nhỏ lỗi duplicate khi người dùng gửi cùng yêu cầu có thể là hành vi bình thường. Nhưng tăng đột biến có thể báo hiệu **bug retry**, lỗi integration, lỗi normalization hoặc migration chưa đầy đủ.

## 22. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `findOne` rồi `insertOne` đã đủ chống trùng | TOCTOU khi hai writer đồng thời | Unique index tại database |
| Khóa trong RAM một pod là đủ | Nhiều pod không chia sẻ mutex | Ràng buộc chung ở database |
| Unique index thường tự so sánh email không phân biệt case | Có thể lưu khác case | emailKey hoặc collation phù hợp |
| Unique email global khi chỉ cần trong tenant | Chặn nhầm tenant khác | Compound unique theo tenant |
| Compound unique theo tenant khi cần email global | Vẫn trùng giữa tenants | Thiết kế key/registry global |
| Nullable field với unique index một trường | Duplicate null/missing | Validation hoặc sparse/partial đúng |
| Sparse unique tự bỏ qua null | Null vẫn có thể được index | Xem partial type filter |
| Partial unique chặn mọi document | Document ngoài partialFilterExpression được phép trùng | Định nghĩa active filter đúng |
| Unique index theo startAt chống overlap | Hai interval khác start có thể overlap | Slot model hoặc coordination |
| Thấy E11000 thì trả success | Có thể là request khác payload | So sánh khóa, payloadHash, trạng thái |
| Catch tất cả lỗi thành duplicate | Che lỗi mạng/permission/validation | Chỉ handle code 11000 khi phù hợp |
| Upsert đồng thời luôn tự update | Có thể nhận E11000 | Unique key chính xác, error path |
| updateMany tự rollback cả batch | Có thể đã cập nhật một phần | Transaction nếu all-or-nothing |
| Unique multikey cấm trùng trong một mảng | Không bảo vệ intra-array duplicates | Validator uniqueItems hoặc logic |
| Transaction thay unique index | Không tự định nghĩa khóa nào duy nhất | Giữ unique constraint |
| Write concern majority tạo uniqueness | Nhầm durability với constraint | Dùng cả hai theo mục tiêu |
| Sharded collection luôn kiểm tra _id global | Có giới hạn khi _id không là shard key | ID globally unique theo thiết kế |
| Index đang build có nghĩa đã bảo vệ ghi | Có thể chưa build hoàn tất | Kiểm soát writer và kiểm tra rollout |
| Retry E11000 vô hạn sẽ thành công | Khóa vẫn trùng, tăng tải | Trả conflict/idempotency-aware result |

## 23. Bài tập thực hành

### Bài 1 — Tái hiện TOCTOU

Hai request gọi `findOne({emailKey:"x"})`, cùng thấy null, sau đó cùng `insertOne`. Vẽ lịch xen kẽ của chúng. Khi chưa có unique index, điều gì có thể xảy ra? Khi đã có index, writer thua nhận lỗi gì?

**Đáp án:** Không index có thể tạo hai document trùng; có unique index thì các write trùng không thể cùng được chấp nhận, thao tác cạnh tranh có thể gặp `E11000`.

### Bài 2 — Index theo tenant

Ứng dụng yêu cầu username duy nhất **trong mỗi tenant**, nhưng các tenant khác nhau được dùng cùng username. Viết index:

~~~javascript
db.users.createIndex(
  { tenantId: 1, usernameKey: 1 },
  { unique: true, name: "uq_tenant_username" }
);
~~~

Giải thích tại sao index chỉ trên `usernameKey` sai phạm vi nghiệp vụ.

### Bài 3 — Update thay đổi key bị từ chối

Trong `lab.accounts`, tạo một account mới trong tenant-1 với emailKey khác, rồi thử update thành `an@example.com`. Giải thích vì sao bị lỗi dù `_id` vẫn khác.

### Bài 4 — Null và missing

Tạo unique single-field index trên `externalCode`. Insert document thiếu field, document có `externalCode: null`, document có `externalCode: "A"`. Document nào bị từ chối? Nếu muốn nhiều document không có code, thiết kế index nào phù hợp?

**Đáp án định hướng:** missing và null sinh khóa null trùng; sparse unique bỏ qua missing, partial theo `$type:"string"` có thể loại missing/null khỏi phạm vi.

### Bài 5 — Booking active

Tạo partial unique index `{roomId:1,startAt:1}` với `partialFilterExpression:{active:true}`. Thử hai booking active trùng, một inactive trùng, rồi update inactive thành active. Mô tả bước nào nhận `E11000`.

### Bài 6 — Booking trùng khoảng thời gian

Hai lịch `09:00–10:00` và `09:30–10:30` có start khác nhau. Unique index trên `startAt` có phát hiện overlap không? Đề xuất mô hình slot hoặc giải pháp coordination phù hợp.

### Bài 7 — Upsert cạnh tranh

Hai worker cùng gọi:

~~~javascript
db.users.updateOne(
  { tenantId: "t1", usernameKey: "an" },
  { $setOnInsert: { displayName: "An" } },
  { upsert: true }
);
~~~

Unique index nào cần có? Có chắc hai writer đều nhận thành công không?

**Đáp án:** Index unique trên cặp tenantId/usernameKey; tối đa một document cùng khóa. Writer khác có thể update hoặc nhận E11000 tùy điều kiện; không bảo đảm cả hai đều thành công.

### Bài 8 — Idempotency key và payload khác nhau

Client gửi hai request có cùng key nhưng payloadHash khác nhau. Request thứ hai bị duplicate. Bạn nên trả “đã thanh toán” hay `409 Conflict`? Tại sao?

**Đáp án:** Phải đọc claim cũ và so sánh payload; nếu khác thì conflict, không coi duplicate là success.

### Bài 9 — Multi-document update

Một `updateMany()` cập nhật emailKey của nhiều document thành cùng một chuỗi. Nếu lỗi unique xuất hiện ở giữa, toàn bộ thao tác có tự rollback không?

**Đáp án:** Không mặc định; nhiều document không phải một transaction. Muốn all-or-nothing cần thiết kế transaction phù hợp.

### Bài 10 — Unique trên mảng

Tạo unique index `{aliases:1}`. Vì sao `["a","a"]` có thể hợp lệ trong một document, nhưng document thứ hai có `["a","b"]` bị từ chối?

**Đáp án:** Unique multikey kiểm tra khóa trùng **giữa document**; không đảm bảo phần tử mảng của cùng document không trùng.

### Bài 11 — Sharding

Collection `accounts` shard theo `tenantId`. Trong ba index sau, cái nào đáp ứng shard-key prefix và có thể làm unique theo quy tắc tương ứng?

~~~javascript
{ emailKey: 1 }
{ tenantId: 1, emailKey: 1 }
{ tenantId: "hashed" }
~~~

**Đáp án:** Compound với tenantId prefix; index chỉ emailKey không hợp lệ cho uniqueness trên ranged sharded collection theo tenant; hashed index không hỗ trợ unique.

### Bài 12 — Triển khai dữ liệu cũ

Collection có:

~~~javascript
{ _id: 1, tenantId: "t1", email: "An@Example.com" }
{ _id: 2, tenantId: "t1", email: "an@example.com" }
~~~

Hãy nêu thứ tự chuẩn hóa emailKey, tìm duplicate, dọn dữ liệu, kiểm soát writer, tạo unique index và thử tải đồng thời. Vì sao quét duplicate lúc 10:00 không đảm bảo index build lúc 10:05 thành công nếu writer vẫn đang ghi?

### Bài 13 — Concurrency test

Chạy thí nghiệm Node.js với 20 `insertOne` có `_id` khác nhưng cùng claimKey. Ghi nhận số request thành công, số `E11000` và count thực tế. Vì sao dùng `Promise.allSettled()` tiện hơn `Promise.all()` cho bài test này?

### Bài 14 — Phân biệt constraint và replication

Giải thích vai trò độc lập của `unique: true` và `writeConcern: { w: "majority" }`. Cơ chế nào định nghĩa “hai document không được trùng email”, cơ chế nào xác định mức xác nhận ghi?

### Bài 15 — Thiết kế một endpoint production

Thiết kế `POST /reservations` với các yêu cầu: một booking active cho mỗi room/slot, lịch sử hủy được lưu, nhiều pod có thể nhận request đồng thời, có idempotency key và không lộ raw MongoDB error. Hãy chỉ ra:

- Compound partial unique index bảo vệ slot.
- Validation đảm bảo các field khóa và active đúng kiểu.
- Luồng claim/idempotency và xử lý E11000.
- Cách xử lý side effect thanh toán và timeout.
- Trường hợp cần transaction đa document.
- Kịch bản test concurrent writers.

## 24. Tổng kết

**Unique index là ràng buộc tại điểm ghi**, nên đặc biệt quan trọng khi nhiều yêu cầu đồng thời cố tạo hoặc cập nhật cùng khóa nghiệp vụ.

Mười điều cần nhớ:

1. **Pre-check không chống TOCTOU**; hãy định nghĩa unique index thật ở database.
2. **Khóa phải đúng phạm vi:** một field, nhiều field, theo tenant hoặc theo trạng thái active.
3. **E11000 là duplicate key conflict**, không tự đồng nghĩa request nghiệp vụ trước đã hoàn thành.
4. **Upsert cũng có race nếu thiếu index**; khi có index, một số request cạnh tranh vẫn có thể nhận lỗi.
5. **Null/missing, sparse, partial, multikey và collation** có quy tắc riêng cần xác định rõ.
6. **Schema validation và chuẩn hóa dữ liệu** bổ sung unique index, không thay thế nó.
7. **Atomicity cấp document khác uniqueness giữa nhiều document**, và transaction đa document là lớp bảo đảm khác.
8. **Idempotency là cả một workflow**: claim unique, payloadHash, trạng thái và khôi phục sau crash/timeout.
9. **Sharded cluster có giới hạn**: unique index phải phù hợp shard key, hashed index không unique.
10. **Migration phải kiểm soát writer trong lúc tạo index**; kiểm tra duplicate trước đó chưa phải bảo đảm dữ liệu không đổi.

### Tài liệu MongoDB chính thức

- [Unique Indexes and Duplicate Values](https://www.mongodb.com/docs/manual/core/index-unique/) — các quy tắc unique, compound, null/missing và multikey.
- [db.collection.createIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/) — cú pháp và option unique.
- [Upsert with Duplicate Values](https://www.mongodb.com/docs/manual/reference/method/db.collection.update/#upsert-with-duplicate-values) — các kết quả có thể xảy ra khi upsert cạnh tranh.
- [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — update, upsert và write concern.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — phạm vi partialFilterExpression và unique partial.
- [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/) — xử lý field thiếu.
- [Collation](https://www.mongodb.com/docs/manual/reference/collation/) — so sánh chuỗi, chữ hoa/thường.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — unique với field mảng.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — shard-key prefix và giới hạn.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — nguyên tử cấp document.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — giao dịch nhiều document.
- [Schema Validation with JSON Schema](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — yêu cầu field đúng kiểu.
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retry theo cơ chế driver.
