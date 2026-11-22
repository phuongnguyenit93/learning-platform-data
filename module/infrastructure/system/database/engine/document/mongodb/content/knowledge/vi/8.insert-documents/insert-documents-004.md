# Lỗi trùng khóa, lỗi validation và kết quả thành công một phần

## 1. Bối cảnh: ghi nhiều document không đồng nghĩa với một giao dịch

Khi thêm document vào MongoDB, một thao tác có thể thất bại vì dữ liệu vi phạm ràng buộc **unique index**, không vượt qua **schema validation**, hoặc vì hệ thống không xác nhận được kết quả ghi theo yêu cầu. Nếu ứng dụng đang nhập nhiều document bằng `insertMany()` hoặc `bulkWrite()`, có thể **một số document đã được ghi thành công trước hoặc cùng lúc với các lỗi khác**.

Ví dụ, một lô nhập năm khách hàng gồm ba hồ sơ hợp lệ, một email đã tồn tại và một tuổi không đạt quy tắc. Điều quan trọng không chỉ là nhận ra “lô có lỗi”, mà còn xác định:

- Document nào chắc chắn đã được ghi, document nào bị từ chối?
- MongoDB dừng ngay tại lỗi đầu tiên hay tiếp tục thử các phần tử khác?
- Lỗi do dữ liệu vi phạm ràng buộc hay do hệ thống chưa xác nhận được thao tác?
- Có được gửi lại toàn bộ lô hay phải đối soát trước?
- Khi nghiệp vụ đòi hỏi tất cả cùng thành công, cần cơ chế nào?

Bài học sử dụng `mongosh` để minh họa quy tắc ở server và **MongoDB Java Sync Driver** để minh họa xử lý lỗi phía ứng dụng Java. Chi tiết cấu trúc exception/response có thể khác theo driver và phiên bản; không nên viết logic bằng cách phân tích nguyên văn thông điệp lỗi.

### 1.1. Các thao tác thường gặp

| Thao tác | Mục đích | Khi có lỗi |
| --- | --- | --- |
| `insertOne(document)` | Thêm một document. | Document đó có thể bị từ chối; nếu đã được xác nhận thành công thì thao tác này đã ghi một document. |
| `insertMany(documents)` | Thêm nhiều document cùng collection. | Ngoài transaction, các phần tử thành công **không tự rollback** khi phần tử khác lỗi. |
| `bulkWrite(operations)` | Gộp insert, update, replace, delete theo mô hình bulk. | Có thể thành công một phần; cần phân biệt loại thao tác và kết quả tương ứng. |
| Transaction nhiều document | Tạo ranh giới giao dịch cho nhiều thao tác. | Nếu giao dịch bị abort, thay đổi của giao dịch không được commit; commit thành công/không rõ kết quả cần xử lý theo ngữ nghĩa transaction. |

**Tính nguyên tử của một lần ghi trên một document** không làm cho một lô `insertMany()` nhiều document trở thành nguyên tử toàn lô. Tùy chọn `ordered` điều khiển cách tiếp tục xử lý sau lỗi, không tự biến lô thành transaction.

## 2. Lỗi trùng khóa: duplicate key (E11000)

MongoDB dùng **unique index** để ngăn các giá trị khóa trùng nhau giữa những document. Mọi collection thông thường đều có index duy nhất trên trường `_id`. Ứng dụng cũng có thể tạo unique index cho những khóa nghiệp vụ như mã khách hàng, mã đơn hoặc email theo từng tenant.

Khi thao tác vi phạm unique index, MongoDB thường trả **mã lỗi 11000**, kèm thông điệp có phần `E11000 duplicate key error`.

### 2.1. Trùng `_id`

~~~javascript
db.accounts.insertOne({
  _id: "ACC-100",
  owner: "Lan",
  status: "ACTIVE"
});

// Thử thêm document khác với cùng _id:
db.accounts.insertOne({
  _id: "ACC-100",
  owner: "Minh",
  status: "ACTIVE"
});
~~~

Lệnh thứ hai bị từ chối vì `_id: "ACC-100"` đã tồn tại. Document ban đầu vẫn giữ nguyên. Lỗi trùng không có nghĩa MongoDB tự ghi đè bản cũ; `insert` có ngữ nghĩa **thêm mới**, còn sửa document phải sử dụng thao tác cập nhật phù hợp.

Thông điệp có thể tương tự:

~~~text
E11000 duplicate key error collection: demo.accounts
index: _id_ dup key: { _id: "ACC-100" }
~~~

Không nên phụ thuộc vào định dạng từng chữ của message. Khi xử lý tự động, ưu tiên **mã lỗi 11000**, thông tin index và định danh nghiệp vụ đã được gán trước.

### 2.2. Trùng unique index khác `_id`

~~~javascript
db.accounts.createIndex(
  { externalCode: 1 },
  { unique: true, name: "uk_external_code" }
);

db.accounts.insertOne({
  _id: "A-01",
  externalCode: "EXT-778",
  owner: "Lan"
});

db.accounts.insertOne({
  _id: "A-02",
  externalCode: "EXT-778",
  owner: "Minh"
});
// E11000 tại uk_external_code
~~~

Hai document có `_id` khác nhau nhưng cùng `externalCode`. Lỗi được phát hiện bằng unique index trên trường nghiệp vụ. **Khả năng tồn tại nhiều giá trị khác nhau của `_id` không đảm bảo toàn bộ document hợp lệ với các index khác**.

### 2.3. Unique theo nhiều trường

Với hệ thống nhiều tenant, email có thể chỉ cần duy nhất **trong cùng tenant**:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true, name: "uk_tenant_email" }
);

db.customers.insertOne({
  _id: "C-1",
  tenantId: "T1",
  emailNormalized: "an@example.com"
});

db.customers.insertOne({
  _id: "C-2",
  tenantId: "T2",
  emailNormalized: "an@example.com"
}); // Hợp lệ: tenant khác

db.customers.insertOne({
  _id: "C-3",
  tenantId: "T1",
  emailNormalized: "an@example.com"
}); // E11000: trùng cặp tenant + email
~~~

Index này đảm bảo tính duy nhất của **tổ hợp khóa**, không đòi mọi tenant đều có email khác nhau. Việc chuẩn hóa email cần có quy tắc nghiệp vụ rõ ràng. Nếu không chuẩn hóa, index mặc định thường phân biệt chữ hoa/chữ thường, trừ khi cấu hình collation phù hợp.

### 2.4. Trường thiếu hoặc `null` cũng cần xem xét

Một unique index trên **một field** thông thường chỉ cho phép một document có entry index là `null`; document thiếu field cũng có thể được lập index như `null`. Vì vậy:

~~~javascript
db.members.createIndex({ memberCode: 1 }, { unique: true });

db.members.insertOne({ _id: 1, displayName: "Lan" });
db.members.insertOne({ _id: 2, displayName: "Minh" });
// Document thứ hai có thể bị E11000:
// cả hai đều thiếu memberCode
~~~

Nếu `memberCode` là tùy chọn và chỉ các giá trị có kiểu string mới cần duy nhất, có thể thiết kế **partial unique index**:

~~~javascript
db.members.createIndex(
  { memberCode: 1 },
  {
    unique: true,
    partialFilterExpression: {
      memberCode: { $type: "string" }
    }
  }
);
~~~

Ví dụ này cần thực hiện trên collection phù hợp hoặc sau khi xử lý index cũ, chứ không tạo chồng một cách tùy tiện rồi kỳ vọng index mới thay đổi tác dụng của index cũ. Partial index chỉ áp ràng buộc unique trong tập document thỏa filter. Cần kiểm tra schema nếu có nhiều kiểu giá trị khác string.

**Lưu ý:** `sparse`, `partial`, unique compound index và unique index trên array có quy tắc riêng. Không nên tổng quát rằng “mọi trường thiếu đều không gây trùng” hoặc “mỗi phần tử array phải duy nhất bên trong một document”. Quy tắc của **unique multikey index** chủ yếu xử lý xung đột khóa giữa các document, nên không tự thay thế validation không cho phần tử trùng trong cùng mảng.

### 2.5. Tạo unique index trên dữ liệu cũ

Nếu collection đã có hai document cùng mã trước khi tạo unique index, lệnh tạo index có thể **thất bại ngay trong giai đoạn build**. Quy trình đúng là kiểm kê dữ liệu hiện hữu, xác định bản ghi chuẩn, sửa dữ liệu trùng theo nghiệp vụ rồi mới tạo index.

Không nên “sửa lỗi” bằng cách xóa ngẫu nhiên một trong hai document, đặc biệt nếu chúng liên quan tới giao dịch, quyền sở hữu hoặc lịch sử kiểm toán.

## 3. Lỗi validation: document không thỏa quy tắc collection

Ngoài unique index, MongoDB có **collection schema validation**. Ứng dụng có thể dùng `$jsonSchema` để quy định trường bắt buộc, kiểu BSON, giá trị tối thiểu/tối đa hoặc các cấu trúc khác.

Khi `validationAction: "error"` và document không hợp lệ, MongoDB thường từ chối ghi với **mã lỗi 121 — DocumentValidationFailure**.

### 3.1. Tạo collection có validator

Ví dụ collection đăng ký cần `email` là chuỗi và `age` là BSON integer tối thiểu 18:

~~~javascript
db.createCollection("registrations", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["email", "age"],
      properties: {
        email: {
          bsonType: "string",
          minLength: 3,
          description: "email phải là chuỗi không rỗng"
        },
        age: {
          bsonType: "int",
          minimum: 18,
          description: "age phải là số nguyên từ 18"
        }
      }
    }
  },
  validationAction: "error",
  validationLevel: "strict"
});

db.registrations.createIndex(
  { email: 1 },
  { unique: true, name: "uk_registration_email" }
);
~~~

Trong ví dụ này có **hai lớp ràng buộc độc lập**:

- `$jsonSchema` xác nhận cấu trúc và miền giá trị (kiểu `int`, tuổi tối thiểu 18).
- Unique index đảm bảo hai document không có cùng `email`.

Validator ở trên chỉ kiểm tra email là string tối thiểu ba ký tự; nó **chưa** kiểm tra cú pháp email đầy đủ hoặc chuẩn hóa chữ hoa/chữ thường. Nếu đó là yêu cầu nghiệp vụ, cần bổ sung validation phù hợp ở ứng dụng và/hoặc collection.

### 3.2. Ví dụ ghi hợp lệ và không hợp lệ

~~~javascript
db.registrations.insertOne({
  _id: "R-001",
  email: "an@example.com",
  age: NumberInt(22)
}); // Thành công

db.registrations.insertOne({
  _id: "R-002",
  email: "binh@example.com",
  age: NumberInt(16)
}); // Lỗi 121: tuổi nhỏ hơn 18

db.registrations.insertOne({
  _id: "R-003",
  email: "chi@example.com",
  age: "22"
}); // Lỗi 121: age là string, không phải BSON int

db.registrations.insertOne({
  _id: "R-004",
  email: "an@example.com",
  age: NumberInt(23)
}); // Lỗi 11000: trùng email
~~~

Việc document mang giá trị mà người dùng thấy là “22” **không có nghĩa kiểu BSON đã đúng**. Với validator yêu cầu `bsonType: "int"`, giá trị string `"22"` sẽ không đạt. Trong Java, kiểu `Integer` thường được mã hóa thành BSON Int32; `Long` thành Int64. Nếu nghiệp vụ chấp nhận cả hai, schema phải mô tả đúng các kiểu được phép.

### 3.3. Validation khi insert và khi update

Validation không chỉ xảy ra lúc thêm mới. Với `validationLevel: "strict"` và `validationAction: "error"`, một update làm document đang hợp lệ trở nên không hợp lệ cũng bị từ chối:

~~~javascript
db.registrations.updateOne(
  { _id: "R-001" },
  { $set: { age: NumberInt(17) } }
);
// Lỗi 121; document ban đầu không đổi bởi update thất bại
~~~

Trong trường hợp dùng replace, phải cẩn thận vì thay toàn bộ document có thể vô tình bỏ các field bắt buộc, gây lỗi validation ngay cả khi giá trị còn lại hợp lệ.

### 3.4. `validationAction` và `validationLevel`

| Thiết lập | Ý nghĩa |
| --- | --- |
| `validationAction: "error"` | Từ chối ghi nếu document vi phạm validator; là hành vi mặc định. |
| `validationAction: "warn"` | Cho phép ghi document không hợp lệ nhưng ghi cảnh báo vào log; không tạo write error 121 do validator. |
| `validationAction: "errorAndLog"` | Từ chối và log lỗi; khả dụng từ MongoDB 8.1 trở lên. |
| `validationLevel: "strict"` | Kiểm tra mọi insert/update theo validator; là mức mặc định. |
| `validationLevel: "moderate"` | Kiểm tra insert và update trên document hiện đã hợp lệ; không áp các quy tắc cho update trên document cũ vốn không đạt validator. |
| `validationLevel: "off"` | Không áp collection validation. |

Các lựa chọn bổ sung có thể thay đổi theo phiên bản MongoDB. Khi vận hành phiên bản cụ thể, cần đọc tài liệu phiên bản đó, nhất là trước khi sử dụng giá trị mới.

Một collection có `warn` có thể chứa document vi phạm schema **mà insert vẫn báo thành công**. Khi điều tra lỗi chất lượng dữ liệu, phải xem config validator thay vì mặc định rằng “có schema là MongoDB đã chặn mọi dữ liệu sai”.

### 3.5. Bypass validation có giới hạn quyền

Một số API cho phép dùng `bypassDocumentValidation` trong các trường hợp được cấp quyền phù hợp, chẳng hạn quá trình migration được kiểm soát. Tùy chọn này có thể bỏ qua **collection validator**, nhưng **không vô hiệu hóa unique index** hoặc các giới hạn cấu trúc BSON.

Không dùng bypass như cách xử lý mặc định cho lỗi 121. Làm vậy khiến dữ liệu sai lọt vào hệ thống, còn ứng dụng khác vẫn giả định mọi document đúng schema.

## 4. Đọc kết quả của một lệnh insert thành công

Với `mongosh`:

~~~javascript
const result = db.registrations.insertOne({
  _id: "R-010",
  email: "dung@example.com",
  age: NumberInt(28)
});

printjson(result);
~~~

Khi được xác nhận thành công theo write concern áp dụng, kết quả thường có dạng:

~~~javascript
{
  acknowledged: true,
  insertedId: "R-010"
}
~~~

Ý nghĩa:

- `acknowledged` cho biết cơ chế xác nhận ghi có được sử dụng.
- `insertedId` là định danh của document được chèn thành công.
- Kết quả này không đồng nghĩa với việc ứng dụng đã hoàn tất mọi thao tác phụ như gửi email, xuất event hoặc cập nhật hệ thống khác.

Với `insertMany()`, thành công toàn bộ thường trả `acknowledged` và tập `insertedIds`. Nhưng khi có lỗi, API có thể **ném exception thay vì trả một object thành công thông thường**; thông tin một phần thành công phải đọc từ dữ liệu kết quả và lỗi trong exception theo driver.

## 5. Ordered insert: lỗi đầu tiên chặn các phần tử phía sau

Theo mặc định, `insertMany()` sử dụng `ordered: true`. Các document được xử lý theo thứ tự trong mảng; khi một document gặp **write error**, các document phía sau không tiếp tục được chèn. Những document trước lỗi đã thành công **vẫn được giữ** nếu không nằm trong transaction bị abort.

### 5.1. Bộ dữ liệu minh họa

Giả sử đã tạo collection và unique index như mục 3; trước khi chạy batch, chỉ có một document được thêm sẵn:

~~~javascript
db.registrations.insertOne({
  _id: "SEED",
  email: "existing@example.com",
  age: NumberInt(30)
});

const batch = [
  { _id: "B-1", email: "one@example.com", age: NumberInt(20) },
  { _id: "B-2", email: "existing@example.com", age: NumberInt(21) },
  { _id: "B-3", email: "three@example.com", age: NumberInt(16) },
  { _id: "B-4", email: "four@example.com", age: NumberInt(27) }
];
~~~

Trong bốn document:

- `B-1` hợp lệ.
- `B-2` vi phạm unique index vì email đã có trong `SEED`.
- `B-3` vi phạm validator vì 16 nhỏ hơn 18.
- `B-4` hợp lệ.

### 5.2. Thực hiện có thứ tự

~~~javascript
try {
  const result = db.registrations.insertMany(
    batch,
    { ordered: true }
  );
  printjson(result);
} catch (error) {
  print("Batch có lỗi:");
  print(error.message);
}
~~~

Với collection xuất phát đúng trạng thái nêu ở trên:

| Phần tử | Diễn biến | Kết quả |
| --- | --- | --- |
| `B-1` | Được xử lý trước; hợp lệ. | **Đã chèn**. |
| `B-2` | Trùng `existing@example.com`. | **Bị từ chối**, mã 11000. |
| `B-3` | Nằm sau lỗi. | **Chưa được thử**; không có lỗi 121 được báo cho phần tử này trong lần ordered đó. |
| `B-4` | Nằm sau lỗi. | **Chưa được thử** dù hợp lệ. |

Ví dụ này cho thấy khác biệt giữa **bị thử và thất bại** với **chưa được thử**. Không thể coi mọi phần tử vắng mặt là “không hợp lệ”.

Kiểm tra trạng thái đã lưu:

~~~javascript
db.registrations.find({
  _id: { $in: ["B-1", "B-2", "B-3", "B-4"] }
}).sort({ _id: 1 });
~~~

Nếu không có lỗi nào khác, chỉ `B-1` xuất hiện. Một exception đã xảy ra, nhưng có một document mới được ghi thành công.

### 5.3. Đừng chạy tiếp ví dụ unordered trên dữ liệu vừa thay đổi

Nếu dùng lại chính collection sau lần ordered ở trên, `B-1` **đã tồn tại**; việc gửi lại batch tạo thêm lỗi trùng `_id`. Để so sánh công bằng với phần tiếp theo, cần dựng lại collection thử nghiệm ở trạng thái chỉ có `SEED`, hoặc dùng collection khác với cùng validator/index và dữ liệu seed. Không thực hiện các thao tác làm sạch này trên database sản xuất.

## 6. Unordered insert: vẫn thử những phần tử khác

Khi truyền `ordered: false`, MongoDB tiếp tục xử lý những document khác sau một write error. Đây thường là lựa chọn phù hợp cho import có các bản ghi **độc lập**, miễn là ứng dụng báo cáo được lỗi của từng bản ghi.

~~~javascript
try {
  const result = db.registrations.insertMany(
    batch,
    { ordered: false }
  );
  printjson(result);
} catch (error) {
  print("Batch có một hoặc nhiều lỗi:");
  print(error.message);
}
~~~

**Giả sử collection được tạo lại từ trạng thái ban đầu, chỉ có `SEED`**:

| Phần tử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| `B-1` | Hợp lệ. | Đã chèn. |
| `B-2` | Trùng email seed. | Write error 11000. |
| `B-3` | Không đạt validator. | Write error 121. |
| `B-4` | Hợp lệ. | Đã chèn. |

Nếu không có vấn đề khác, hai document `B-1` và `B-4` được chèn, hai document còn lại thất bại. API vẫn có thể ném **lỗi bulk tổng hợp**, dù đã có dữ liệu được lưu.

MongoDB có thể **đổi thứ tự thực thi** các thao tác unordered để cải thiện hiệu năng. Vì vậy, không xây quy tắc nghiệp vụ dựa vào giả định rằng `B-1` luôn chạy trước `B-4` trong chế độ này. Với những document độc lập, thứ tự thường không quan trọng; với những thao tác phụ thuộc nhau, nó có thể rất quan trọng.

### 6.1. So sánh `ordered` và `unordered`

| Thuộc tính | `ordered: true` | `ordered: false` |
| --- | --- | --- |
| Mặc định của `insertMany()` | Có. | Phải chỉ định. |
| Khi phần tử gặp write error | Dừng các phần tử phía sau. | Tiếp tục thử những phần tử còn lại. |
| Thứ tự | Giữ ý nghĩa thứ tự trong batch. | Không được phụ thuộc thứ tự thực thi. |
| Số lỗi có thể được báo | Thường một write error đầu tiên cho chuỗi ordered. | Có thể nhiều write error. |
| Có tự rollback phần tử đã chèn? | Không, khi ngoài transaction. | Không, khi ngoài transaction. |
| Ví dụ phù hợp | Quy trình dừng khi phát hiện dòng lỗi đầu tiên. | Import độc lập, muốn thu thập nhiều lỗi trong một lần chạy. |
| Rủi ro cần quản lý | Bỏ qua các dòng hợp lệ sau lỗi. | Cần thống kê chính xác các thành công và lỗi, không dựa vào thứ tự. |

**Ordered không có nghĩa là atomic.** Một batch ordered cũng có thể thành công một phần. **Unordered không có nghĩa là bỏ qua lỗi.** API báo lỗi cho những thao tác thất bại, trong khi phần tử khác vẫn có thể được ghi.

## 7. Cấu trúc lỗi và kết quả khi ghi theo lô

MongoDB phân biệt các nhóm lỗi, trong đó đặc biệt quan trọng là:

- **`writeErrors`:** lỗi khi xử lý từng thao tác ghi, ví dụ trùng unique key hoặc document vi phạm validator.
- **`writeConcernErrors`:** lỗi không đáp ứng điều kiện xác nhận ghi trong thời hạn yêu cầu, ví dụ chờ replica xác nhận quá lâu.
- **Partial write result:** thông tin về thao tác đã được xử lý thành công, như số insert đã được chấp nhận.

Ví dụ **minh họa cấu trúc logic** của một lỗi unordered:

~~~javascript
{
  writeErrors: [
    {
      index: 1,
      code: 11000,
      errmsg: "E11000 duplicate key error ..."
    },
    {
      index: 2,
      code: 121,
      errmsg: "Document failed validation"
    }
  ],
  writeConcernErrors: [],
  nInserted: 2
}
~~~

Đây không phải cam kết về chính xác tên property được bọc ngoài ở mọi version driver. Trong `mongosh`, lỗi bulk có các trường liên quan như `writeErrors`, `writeConcernErrors` và số lượng đã chèn; Java driver dùng các phương thức trên exception/result.

Chỉ số `index` trong write error thường chỉ **vị trí zero-based của thao tác trong danh sách ban đầu**. Ví dụ `index: 1` là phần tử thứ hai. Hãy gắn một **mã đầu vào ổn định** cho mỗi phần tử để có thể đối chiếu từ chỉ số đến bản ghi mà không phụ thuộc nội dung lỗi in ra.

### 7.1. Lỗi 11000 và 121 khác nhau về hành động khắc phục

| Mã | Tên/thông điệp phổ biến | Nguyên nhân thường gặp | Hành động phù hợp |
| --- | --- | --- | --- |
| **11000** | `DuplicateKey` / `E11000 duplicate key` | `_id` hoặc một unique index khác bị trùng. | Xác định index, giá trị trùng và chính sách gộp, bỏ qua hoặc cập nhật. |
| **121** | `DocumentValidationFailure` | Document vi phạm collection validator. | Sửa payload/schema mapping hoặc quy tắc nghiệp vụ; kiểm tra validator hiện hành. |
| **64** trong nhiều tình huống | `WriteConcernTimeout` | Thao tác chưa được xác nhận theo write concern trong thời gian mong đợi. | Kiểm tra tình trạng replica, kết quả hiện có và chính sách retry/đối soát. |

**Không tự động sửa tất cả lỗi bằng retry.** Lỗi 11000 do giá trị trùng và lỗi 121 do kiểu dữ liệu sai thường không biến mất khi gửi lại đúng cùng payload. Một lỗi write concern hoặc gián đoạn mạng lại đòi hỏi xác định **trạng thái ghi có thể đã xảy ra**, chứ không giả định chắc chắn thất bại.

### 7.2. Trường `writeConcernError` không phải khẳng định “đã rollback”

Giả sử một lệnh yêu cầu `writeConcern: { w: "majority", wtimeout: 100 }` trong replica set. Primary có thể đã chấp nhận ghi nhưng việc xác nhận của số replica cần thiết không đến trong 100 ms. Driver/server có thể báo lỗi write concern.

Đó là vấn đề **mức độ xác nhận/durability**, khác với document bị validator từ chối. Không được giải thích mọi `writeConcernError` là “chưa document nào được ghi”. Trước khi retry, cần có mã idempotent và chiến lược kiểm tra kết quả.

### 7.3. Kết quả một phần cần lưu dưới dạng trạng thái từng bản ghi

Một hệ thống nhập dữ liệu nên phân biệt:

~~~text
SUCCESS_CONFIRMED   Được xác nhận đã ghi thành công
REJECTED_DUPLICATE  Bị từ chối do trùng unique key
REJECTED_VALIDATION Bị từ chối do schema validation
NOT_ATTEMPTED       Ordered dừng trước khi xử lý dòng này
UNKNOWN             Không thể xác định chắc chắn sau lỗi mạng/xác nhận
~~~

Các trạng thái trên là **ví dụ thiết kế của ứng dụng**, không phải enum do MongoDB định nghĩa. Với kết quả có thể không chắc chắn, tránh tự suy ra `FAILED` hoặc `SUCCESS` chỉ từ một thông điệp timeout.

## 8. Xử lý exception trong `mongosh`

Một cách học và quan sát là bắt exception, in thông tin kỹ thuật rồi xác minh dữ liệu đã có:

~~~javascript
try {
  const result = db.registrations.insertMany(
    batch,
    { ordered: false }
  );
  printjson({ status: "ALL_INSERTED", result });
} catch (error) {
  print("BULK_ERROR");
  print("message: " + error.message);
  printjson(error.writeErrors);
  printjson(error.writeConcernErrors);
  printjson(error.result);
}
~~~

Tùy phiên bản `mongosh`, trường trên exception có thể khác hoặc không xuất hiện; có thể in thông tin exception phù hợp khi học và đối chiếu với tài liệu version đang chạy. Không đưa nguyên document hoặc payload nhạy cảm vào log production chỉ để điều tra lỗi.

Sau đó, **đọc lại theo ID ứng dụng đã biết**:

~~~javascript
db.registrations.find(
  { _id: { $in: ["B-1", "B-2", "B-3", "B-4"] } },
  { _id: 1, email: 1, age: 1 }
).sort({ _id: 1 });
~~~

Đọc lại giúp biết trạng thái hiện tại, nhưng phải nhớ rằng có thể có nhiều tiến trình khác đồng thời ghi/sửa dữ liệu. Trong hệ thống có cạnh tranh hoặc retry, cần kiểm tra thêm mã import, version hoặc dấu vết idempotency, thay vì chỉ thấy một `_id` tồn tại rồi kết luận đó chắc chắn là bản do lần batch hiện tại tạo ra.

## 9. Java Sync Driver: bắt lỗi và lấy thông tin thành công một phần

Trong ứng dụng Java, `MongoCollection<Document>` cung cấp `insertOne`, `insertMany` và `bulkWrite`.

Các lớp kết quả/lỗi thường gặp:

| Java API | Thành công | Lỗi cần nhận diện |
| --- | --- | --- |
| `insertOne` | `InsertOneResult` | `MongoWriteException` cho write error đơn lẻ, cùng các dạng exception kết nối/write concern tương ứng. |
| `insertMany` | `InsertManyResult` | `MongoBulkWriteException` cho lỗi bulk. |
| `bulkWrite` (collection-level) | `BulkWriteResult` | `MongoBulkWriteException` và lỗi kết nối/xác nhận khác tùy tình huống. |

### 9.1. Ví dụ Java với `insertMany` unordered

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.InsertManyOptions;
import org.bson.Document;

import java.util.List;

public class RegistrationImporter {
    public static void importBatch(MongoCollection<Document> registrations) {
        List<Document> documents = List.of(
            new Document("_id", "B-1")
                .append("email", "one@example.com")
                .append("age", 20),
            new Document("_id", "B-2")
                .append("email", "existing@example.com")
                .append("age", 21),
            new Document("_id", "B-3")
                .append("email", "three@example.com")
                .append("age", 16),
            new Document("_id", "B-4")
                .append("email", "four@example.com")
                .append("age", 27)
        );

        try {
            var result = registrations.insertMany(
                documents,
                new InsertManyOptions().ordered(false)
            );
            System.out.println(
                "All documents inserted: "
                + result.getInsertedIds().size()
            );
        } catch (MongoBulkWriteException e) {
            System.err.println(
                "Acknowledged successful inserts: "
                + e.getWriteResult().getInsertedCount()
            );

            e.getWriteErrors().forEach(writeError -> {
                int inputIndex = writeError.getIndex();
                int code = writeError.getCode();

                System.err.printf(
                    "Input index %d, code %d, id %s%n",
                    inputIndex,
                    code,
                    documents.get(inputIndex).getString("_id")
                );
            });

            if (e.getWriteConcernError() != null) {
                System.err.println(
                    "Write concern error also occurred"
                );
            }
        }
    }
}
~~~

Trong Java Sync Driver, `MongoBulkWriteException` cho phép đọc các write error và phần kết quả ghi thành công. Phần `e.getWriteResult().getInsertedCount()` hữu ích để biết số insert đã được server xác nhận khi kết quả bulk có write errors.

Đoạn code giả định lỗi thuộc loại bulk và chỉ minh họa **cách quan sát**. Khi viết importer thực tế, cần:

- Xử lý thêm lỗi kết nối/timeout hoặc trường hợp kết quả không được xác nhận đầy đủ.
- Không chỉ đếm thành công mà phải ánh xạ trạng thái theo ID đầu vào.
- Không ghi raw email, tài liệu cá nhân hoặc chi tiết validator chứa dữ liệu nhạy cảm vào log.
- Không mặc định mọi error đều có cùng API hoặc mọi driver version dùng đúng class như nhau.
- Không dùng mảng `documents` thay đổi thứ tự sau khi gửi lệnh; `writeError.getIndex()` phải được ánh xạ về danh sách đầu vào gốc.

Trong ví dụ, `append("age", 20)` với `Integer` thông thường được driver mã hóa thành BSON Int32, phù hợp với validator yêu cầu `bsonType: "int"`. Nếu thay bằng `20L`, trường có thể được mã hóa thành BSON Int64 và không đạt validator đang đặt.

### 9.2. Với `insertOne`

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class SingleInsertExample {
    public static void insert(MongoCollection<Document> collection) {
        try {
            collection.insertOne(
                new Document("_id", "B-2")
                    .append("email", "existing@example.com")
                    .append("age", 21)
            );
        } catch (MongoWriteException e) {
            int code = e.getError().getCode();

            if (code == 11000) {
                System.err.println("Duplicate unique key");
            } else if (code == 121) {
                System.err.println("Schema validation rejected document");
            } else {
                throw e;
            }
        }
    }
}
~~~

Mã lỗi giúp phân loại để trả thông báo nghiệp vụ hoặc quyết định hành động tiếp theo. Tuy nhiên, không nên biến `11000` thành “thành công” theo mặc định: đó có thể là một bản ghi **khác** đã dùng trùng khóa, cần so sánh định danh và nội dung theo chính sách nghiệp vụ.

### 9.3. Spring Data MongoDB

Với `MongoTemplate`, Spring Data có thể **dịch exception của driver** sang hệ thống exception truy cập dữ liệu của Spring, ví dụ `DuplicateKeyException` cho lỗi unique. API bulk của Spring Data cũng có các loại exception/kết quả và cách bọc khác nhau theo phiên bản.

Nếu ứng dụng cần thông tin *từng phần tử* trong một batch, hãy kiểm tra đúng abstraction đang dùng, nguyên nhân gốc và contract của phiên bản. Không nên chỉ catch một lớp exception tổng quát rồi trả HTTP 500 mà bỏ qua các phần tử đã ghi.

Validation ở Java như `@NotNull`, `@Email` hoặc `@Min` có thể hữu ích ở tầng API, nhưng không thay thế unique index hay collection validator: một tiến trình khác có thể ghi trực tiếp qua driver, và kiểm tra trước ở ứng dụng có thể bị race condition.

## 10. `bulkWrite()` và kết quả thành công một phần

`bulkWrite()` cho phép gửi nhiều thao tác: insert, update, replace và delete. Kết quả bulk có các bộ đếm tương ứng như `insertedCount`, `matchedCount`, `modifiedCount`, `deletedCount` hoặc `upsertedCount`, tùy API.

~~~javascript
db.inventory.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "P1", stock: 10 }
      }
    },
    {
      updateOne: {
        filter: { _id: "P2" },
        update: { $inc: { stock: 5 } }
      }
    },
    {
      insertOne: {
        document: { _id: "P3", stock: 7 }
      }
    }
  ],
  { ordered: false }
);
~~~

Kết quả `updateOne` có thể **matched = 0** mà không có write error, ví dụ không tồn tại sản phẩm `P2`. Điều đó khác với insert bị lỗi trùng. Một bulk result báo “operation thành công” ở mức lệnh không chứng minh mọi mục tiêu nghiệp vụ đều được thực hiện.

Không nên dùng unordered bulk khi các thao tác **phụ thuộc thứ tự**, ví dụ trước tiên tạo document rồi ngay lập tức update chính document đó trong cùng lô. MongoDB có thể thực hiện unordered operations theo thứ tự khác; nên tách các giai đoạn phụ thuộc hoặc dùng transaction và cách điều phối phù hợp.

### 10.1. Index của lỗi trong bulk

Nếu thao tác thứ ba bị lỗi, `writeErrors.index = 2` tham chiếu vị trí của thao tác thứ ba trong danh sách bulk, bất kể thao tác là insert hay update. Do đó, bảng đối chiếu phải lưu:

~~~text
index 0 -> insert product P1
index 1 -> increment stock P2
index 2 -> insert product P3
~~~

Không thể luôn lấy `index` rồi coi đó là index của một danh sách riêng chỉ gồm insert nếu bulk còn có update/delete.

### 10.2. Batch lớn

Với high-level API, driver có thể chia danh sách rất dài thành nhiều batch theo giới hạn giao thức, ví dụ `maxWriteBatchSize`. Vì thế, một call ứng dụng có thể tương ứng nhiều yêu cầu ghi đến server. Ngoài transaction, một lỗi ở batch sau **không tự hoàn tác** những document đã được ghi trong batch trước.

Hệ thống nhập liệu nên đánh dấu từng khoảng hoặc từng định danh đã được xử lý, thay vì coi toàn bộ tệp chỉ có một cờ “DONE/FAILED”.

## 11. Transaction: khi nào cần tất cả cùng thành công?

Nếu nghiệp vụ yêu cầu **không chấp nhận trạng thái chỉ thêm một phần**, cần cân nhắc multi-document transaction trong deployment MongoDB được hỗ trợ.

Ví dụ, một thao tác nghiệp vụ tạo đơn hàng và ghi lịch sử thanh toán phải cùng thuộc một giao dịch:

~~~text
start transaction
    insert order
    insert payment record
    update reserved inventory
commit transaction
~~~

Nếu một thao tác trong transaction gây lỗi buộc giao dịch phải abort, các thay đổi của transaction không được commit. Ứng dụng phải xử lý đúng quy trình abort/retry/commit và các nhãn lỗi giao dịch (*error labels*) theo tài liệu driver.

Điểm cần phân biệt:

- **`ordered: true` ngoài transaction:** lỗi sau một insert vẫn để lại những insert trước đó.
- **`ordered: false` ngoài transaction:** có thể để lại nhiều insert thành công xen lẫn insert bị từ chối.
- **Transaction đã abort:** không có trạng thái “commit một phần” cho các thay đổi của transaction.
- **Commit trả kết quả không chắc chắn:** ứng dụng cần cơ chế xử lý *unknown transaction commit result* theo driver; không nên xem timeout là chứng cứ đã rollback.

Transaction cũng có chi phí: tài nguyên, thời gian giữ snapshot, khả năng xung đột và giới hạn vận hành. Không nên bọc hàng triệu document độc lập vào một transaction khổng lồ chỉ để khỏi xử lý trạng thái từng dòng. Với import có thể chấp nhận một phần, unordered + báo cáo chính xác thường là lựa chọn thực dụng hơn.

## 12. Retry: bài toán khó nhất sau partial success

Giả sử lô unordered có bốn dòng:

~~~text
B-1: inserted
B-2: E11000
B-3: E121
B-4: inserted
~~~

Nếu gửi lại **nguyên vẹn** cả bốn dòng:

- `B-1` và `B-4` có thể phát sinh E11000 vì đã tồn tại.
- `B-2` vẫn trùng khóa.
- `B-3` vẫn vi phạm validator.
- Báo cáo số lỗi tăng, trong khi dữ liệu không thay đổi.

Lỗi mới không đồng nghĩa lần chạy trước chưa chèn gì. Đây là nguyên nhân phổ biến của việc retry mù làm rối nhật ký import.

### 12.1. Gán định danh ổn định trước khi gửi

Ví dụ, mỗi bản ghi đến từ hệ thống ngoài có `sourceSystem` và `externalId` duy nhất. Có thể tạo unique index trên cặp này hoặc sinh `_id` bền vững từ định danh bên ngoài:

~~~javascript
{
  _id: "CRM|customer-481",
  sourceSystem: "CRM",
  externalId: "customer-481",
  fullName: "Khách hàng A"
}
~~~

Nếu lần ghi bị mất kết nối, ứng dụng có khóa ổn định để **truy vấn đối soát** trước khi quyết định insert lại, cập nhật hay báo conflict.

Không nên tạo `ObjectId()` mới ở mỗi lần retry khi nghiệp vụ cần cùng một sự kiện chỉ được áp dụng một lần: mỗi lần có `_id` khác nhau sẽ khó phát hiện bản ghi trùng về nghiệp vụ.

### 12.2. Upsert có thể hỗ trợ idempotency

Nếu quy tắc là “tạo khi chưa tồn tại, không sửa nếu đã có”, có thể dùng `$setOnInsert`:

~~~javascript
db.importedCustomers.updateOne(
  { _id: "CRM|customer-481" },
  {
    $setOnInsert: {
      sourceSystem: "CRM",
      externalId: "customer-481",
      fullName: "Khách hàng A",
      importedAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Khi document đã tồn tại, update không làm thay đổi trường trong `$setOnInsert`; khi chưa có, MongoDB có thể chèn mới. Tuy nhiên, điều này chỉ đúng theo **ngữ nghĩa “giữ bản đã có”**. Nếu dữ liệu mới khác bản cũ, ứng dụng phải biết đó là bản cập nhật hợp lệ, dữ liệu xung đột hay duplicate thật.

Với những upsert cạnh tranh, vẫn cần unique index và xử lý lỗi có thể xảy ra do race condition; không được suy ra rằng `upsert: true` loại bỏ mọi khả năng E11000.

### 12.3. Phân nhóm khả năng retry

| Loại kết quả | Có nên tự retry nguyên payload? | Cách xử lý |
| --- | --- | --- |
| E11000 cùng mã và nội dung nghiệp vụ đã tồn tại | Thường không cần insert lại. | Đối chiếu record hiện hữu; xác nhận duplicate được chấp nhận hay conflict. |
| E11000 do trùng mã nhưng nội dung khác | Không. | Trả conflict hoặc quy trình merge theo nghiệp vụ. |
| E121 do thiếu/nhầm kiểu field | Không, nếu dữ liệu không đổi. | Sửa validation/mapping hoặc đưa vào hàng sửa dữ liệu. |
| Ordered dừng: phần tử chưa được thử | Có thể gửi những phần tử này sau khi xử lý nguyên nhân, theo ID ổn định. | Không trộn với các phần tử đã chèn; phân biệt trạng thái. |
| Lỗi mạng/timeout, chưa rõ ghi đã xảy ra | Chỉ retry có kiểm soát. | Dùng retryable writes theo driver khi phù hợp; đọc/đối soát bằng khóa ổn định. |
| Write concern timeout | Không coi là “chưa ghi”. | Kiểm tra trạng thái xác nhận và dữ liệu, rồi quyết định theo yêu cầu durability. |

MongoDB driver có thể hỗ trợ **retryable writes** khi topology, loại thao tác và cấu hình cho phép. Điều đó không thay thế idempotency của *nghiệp vụ*; chẳng hạn việc phát lại một sự kiện thanh toán hoặc tăng bộ đếm từ ứng dụng vẫn cần quy tắc xử lý trùng.

## 13. Thiết kế API trả kết quả cho một phần thành công

Một API nhập danh sách 100 khách hàng không nên chỉ trả:

~~~json
{ "success": false, "message": "Import failed" }
~~~

Thông điệp đó che giấu khả năng 98 hồ sơ đã được ghi. API có thể trả một báo cáo theo từng dòng, chẳng hạn:

~~~json
{
  "importId": "IMP-2026-11-14-001",
  "received": 4,
  "inserted": 2,
  "rejected": 2,
  "unknown": 0,
  "items": [
    { "sourceId": "B-1", "status": "INSERTED" },
    { "sourceId": "B-2", "status": "DUPLICATE", "errorCode": 11000 },
    { "sourceId": "B-3", "status": "INVALID", "errorCode": 121 },
    { "sourceId": "B-4", "status": "INSERTED" }
  ]
}
~~~

Đây là **contract ví dụ của ứng dụng**, không phải response chuẩn từ MongoDB. Có thể dùng một mã HTTP phù hợp với giao thức API (ví dụ một response thành công có báo cáo lỗi từng dòng, hoặc mã được quy ước cho partial result), nhưng quan trọng hơn là client hiểu chính xác đâu là dữ liệu đã chèn và đâu là phần cần sửa.

API cũng nên ghi rõ:

- `importId` và phiên bản nguồn dữ liệu.
- ID ổn định của từng dòng hoặc khóa idempotency.
- Trạng thái `NOT_ATTEMPTED` nếu ordered dừng trước dòng đó.
- Trạng thái `UNKNOWN` khi không đủ thông tin xác nhận.
- Mã lỗi kỹ thuật có thể xử lý tự động, thông báo nghiệp vụ không chứa thông tin bí mật.
- Thời điểm xử lý, tổng số thử/đã chèn/từ chối và chính sách retry.

Khi thông tin lỗi lớn hoặc có dữ liệu cá nhân, nên tách log kỹ thuật có kiểm soát truy cập khỏi thông điệp gửi cho người dùng cuối.

## 14. Validation ở nhiều tầng và race condition

Một dịch vụ Java có thể kiểm tra dữ liệu trước khi gọi MongoDB:

~~~text
HTTP request
   |
   v
Bean Validation / DTO validation
   |
   v
Business rules / normalization
   |
   v
MongoDB driver
   |
   v
Collection validator + unique indexes
~~~

Các tầng có mục đích khác nhau:

1. **DTO/Bean Validation:** trả lỗi thân thiện sớm, ví dụ thiếu email hoặc tuổi âm.
2. **Business validation:** quy tắc phụ thuộc nghiệp vụ, ví dụ chỉ cho phép một loại tài khoản với một tenant.
3. **Collection validator:** giúp dữ liệu có cấu trúc đúng dù truy cập từ tiến trình khác.
4. **Unique index:** là ràng buộc cuối cùng chống xung đột đồng thời trên khóa unique.

Một đoạn code kiểu “kiểm tra email chưa tồn tại rồi insert” không thay thế unique index:

~~~javascript
const exists = db.registrations.findOne({
  email: "an@example.com"
});

if (!exists) {
  db.registrations.insertOne({
    email: "an@example.com",
    age: NumberInt(24)
  });
}
~~~

Hai request đồng thời đều có thể thấy `exists == null` trước khi request nào insert. Chỉ unique index hoặc cơ chế nhất quán thích hợp mới ngăn được cả hai tạo bản trùng. Ứng dụng cần bắt lỗi E11000 và chuyển thành quyết định nghiệp vụ phù hợp.

Tương tự, collection validator không nên được “sửa” bằng cách thay đổi schema trong production để vừa một payload sai, nếu thực sự vấn đề là mapping DTO, kiểu BSON hoặc dữ liệu người dùng. Việc thay validator cần quy trình migration và đánh giá tác động.

## 15. Quan sát và đối soát một lô import thực tế

Giả sử một tệp có 50.000 dòng, xử lý theo từng lô 1.000. Một thiết kế dễ phục hồi có thể dùng:

~~~text
Tệp nguồn + importId + checksum
                 |
                 v
      Chuẩn hóa và validate ở ứng dụng
                 |
                 v
      Tạo ID ổn định cho từng dòng
                 |
                 v
      Gửi batch ordered/unordered
                 |
                 v
      Thu kết quả đã xác nhận và writeErrors
                 |
                 v
      Ghi bảng trạng thái theo sourceId
                 |
        +--------+--------+
        |                 |
    Thành công       Lỗi/không rõ
        |                 |
        v                 v
    Đánh dấu DONE     Sửa dữ liệu hoặc đối soát
                          |
                          v
                    Retry có kiểm soát
~~~

### 15.1. Các chỉ số nên theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| `receivedCount` | Tổng số dòng đầu vào. |
| `attemptedCount` | Số dòng đã được gửi/thử xử lý, có phân biệt trạng thái chưa rõ. |
| `insertedCount` | Số insert được xác nhận thành công. |
| `duplicateCount` | Số dòng bị E11000, tách theo index nếu cần. |
| `validationFailureCount` | Số dòng bị E121, phân nhóm theo quy tắc lỗi. |
| `notAttemptedCount` | Dòng chưa xử lý vì ordered dừng hoặc job bị dừng. |
| `unknownCount` | Dòng không đủ thông tin kết luận do lỗi mạng/xác nhận. |
| `reconciledCount` | Dòng trước đó không rõ đã được đối soát qua khóa ổn định. |
| `retryCount` | Số lần thử lại, phân theo nguyên nhân. |

Không nên tính tổng `received = inserted + duplicate + invalid` nếu vẫn có phần tử chưa được thử hoặc kết quả không rõ. Hệ thống cần bảo đảm **mỗi dòng có đúng một trạng thái hiện tại**, và có lịch sử chuyển trạng thái để điều tra.

### 15.2. Khi dữ liệu đã có trước khi import

Có thể có cùng external ID trong database vì một lần import cũ đã chạy thành công. Lúc gặp E11000, điều cần làm là so sánh:

- Có đúng **cùng nguồn** và **cùng định danh nghiệp vụ** không?
- Payload có cùng version/nội dung không?
- Có phải request retry của cùng import hay hai nguồn khác nhau đang tranh chấp?
- Chính sách là skip, update, merge hay trả conflict?
- Có cần ghi audit hay phát event phụ thuộc vào việc “mới insert” hay “đã tồn tại” không?

Như vậy, E11000 là **tín hiệu về ràng buộc duy nhất**, chưa phải quyết định nghiệp vụ rằng bản ghi đang tồn tại “giống hệt” bản mới.

## 16. Các tình huống dễ hiểu sai

### Tình huống A: Batch có một dòng sai tuổi ở giữa

~~~text
Input: A hợp lệ, B tuổi 16, C hợp lệ
Validator: age >= 18
~~~

- Với `ordered: true`: A được chèn, B bị lỗi 121, C không được thử.
- Với `ordered: false`: A và C có thể được chèn, B bị lỗi 121.
- Ngoài transaction, không có rollback tự động cho A khi B lỗi.

### Tình huống B: Hai bản ghi cùng `_id` trong chính batch

~~~javascript
[
  { _id: "X1", email: "a@example.com", age: NumberInt(20) },
  { _id: "X1", email: "b@example.com", age: NumberInt(21) }
]
~~~

Unique index trên `_id` không cho phép cả hai tồn tại đồng thời trong cùng collection. Với ordered, phần tử đầu có thể được chèn rồi phần tử thứ hai lỗi; với unordered, **không được phụ thuộc bản nào sẽ được thực thi trước**. Nếu hai payload có ý nghĩa khác nhau, đây là lỗi định danh ở nguồn cần sửa, không thể chấp nhận “bản nào thắng cũng được”.

### Tình huống C: Batch báo exception nhưng thấy document cuối cùng trong database

Điều này có thể hoàn toàn phù hợp với `ordered: false`: phần tử giữa lỗi nhưng phần tử cuối đã được chèn. Khi có lỗi mạng hoặc writer khác chạy đồng thời, còn cần đối soát ID để xác định nguồn của bản ghi.

### Tình huống D: `validationAction: "warn"`

Document không đạt validator có thể **vẫn được chèn**, còn hệ thống ghi warning. Vì thế không thấy lỗi 121 không chứng minh document đã đạt mọi quy tắc; phải kiểm tra cấu hình validator và validation ở tầng ứng dụng.

### Tình huống E: MongoDB xác nhận write nhưng email thông báo không gửi được

Insert và gửi email là hai hệ thống khác nhau. Không thể coi lỗi gửi email là lý do gửi lại nguyên `insertMany`. Nên có cơ chế outbox/event idempotent hoặc workflow riêng để retry bước thông báo mà không tạo thêm dữ liệu.

### Tình huống F: Một số dòng không có email dưới unique index

Nếu unique index đơn trên email không phải partial, nhiều dòng thiếu email có thể gây E11000 do entry `null`. Trường hợp email tùy chọn cần schema/index riêng phù hợp, không phải xóa toàn bộ unique constraint.

### Tình huống G: Dùng toàn bộ lô trong transaction để “bảo đảm không mất dòng”

Transaction giúp đảm bảo tính nguyên tử của thay đổi thuộc một giao dịch, nhưng không xử lý hộ dữ liệu sai, không bảo đảm tệp import sẽ luôn hợp lệ và không miễn phí về hiệu năng. Với tệp rất lớn, chia batch, checkpoint và đối soát thường thực dụng hơn một transaction cực lớn.

## 17. Bài tập thực hành

### Bài 1 — Dự đoán trạng thái trong collection

Giả sử collection `students` có unique index trên `studentCode`, validator yêu cầu `age >= 16`, và đã tồn tại `studentCode: "S1"`. Một batch gồm:

~~~javascript
[
  { _id: 101, studentCode: "S2", age: NumberInt(17) },
  { _id: 102, studentCode: "S1", age: NumberInt(18) },
  { _id: 103, studentCode: "S3", age: NumberInt(15) },
  { _id: 104, studentCode: "S4", age: NumberInt(19) }
]
~~~

Hãy lập bảng cho từng document khi:

1. `ordered: true`, ngoài transaction.
2. `ordered: false`, ngoài transaction.
3. Phải abort transaction do một write error trong batch.

**Gợi ý:** ở trường hợp 1, chỉ S2 được chèn; S1 gây lỗi; S3 và S4 chưa được thử. Ở trường hợp 2, S2 và S4 có thể được chèn, S1 và S3 bị từ chối. Ở trường hợp 3, nếu transaction abort, không commit thay đổi của transaction, dù một số thao tác đã chạy trước đó.

### Bài 2 — Chọn index phù hợp

Nghiệp vụ yêu cầu mỗi người bán được dùng một SKU duy nhất; SKU giống nhau giữa người bán khác nhau là hợp lệ.

~~~javascript
{ sellerId: "SELLER-A", sku: "KB-01" }
{ sellerId: "SELLER-B", sku: "KB-01" }
~~~

Hãy tạo compound unique index cho `(sellerId, sku)` và thử thêm document có cùng cặp. Thảo luận cách xử lý trường `sku` thiếu/null và việc chuẩn hóa chữ hoa/chữ thường theo nghiệp vụ.

### Bài 3 — Phân biệt xác nhận không đầy đủ và validation

Một lệnh `insertMany` báo:

~~~text
writeErrors: [ { index: 2, code: 121, ... } ]
writeConcernErrors: [ ... timeout ... ]
~~~

Hãy giải thích tại sao không thể suy ra toàn batch “chắc chắn chưa ghi”. Xác định cần lưu những ID nào và dùng cách đối soát nào trước khi quyết định retry.

### Bài 4 — Thiết kế import có thể chạy lại

Một tệp CSV từ hệ thống CRM được gửi lại hàng ngày; đôi khi trùng khách hàng, đôi khi sai email. Hãy đề xuất:

- Khóa ID ổn định cho mỗi khách hàng.
- Unique index bảo vệ khóa nghiệp vụ.
- Quy tắc “trùng cùng nội dung” so với “trùng khác nội dung”.
- Danh sách trạng thái từng dòng, bao gồm `UNKNOWN`.
- Phương án sửa dữ liệu lỗi 121 và chạy lại chỉ những dòng thích hợp.

### Bài 5 — Java exception handling

Viết một hàm Java nhận `List<Document>`, dùng `insertMany(..., ordered(false))`, và trả một danh sách trạng thái theo ID. Bảo đảm hàm phân biệt được lỗi 11000, 121 và lỗi không xác định. Hàm cần ghi rõ chính sách khi nhận lỗi mạng mà không có partial result đáng tin cậy.

## 18. Các ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu chính xác |
| --- | --- |
| “`insertMany` lỗi thì toàn batch rollback.” | Ngoài transaction, các document thành công có thể đã được lưu. |
| “`ordered: true` nghĩa là atomic.” | `ordered` chỉ quy định cách tiếp tục sau lỗi ghi. |
| “`ordered: false` sẽ bỏ qua lỗi mà không báo.” | Vẫn có write errors, dù các phần tử hợp lệ khác được xử lý. |
| “Một bulk exception nghĩa là không có document nào thành công.” | Cần xem partial result và/hoặc đối soát theo ID. |
| “Mọi dòng không có trong database đều sai.” | Có thể có dòng chưa được thử do ordered dừng hoặc job bị ngắt. |
| “E11000 chỉ do trùng `_id`.” | Có thể do bất kỳ unique index nào, kể cả compound index. |
| “Đã check tồn tại trước insert thì không cần unique index.” | Kiểm tra rồi insert có race condition khi nhiều request đồng thời. |
| “Field thiếu không bao giờ liên quan unique index.” | Unique index có quy tắc về `null` và field thiếu; cần thiết kế partial/sparse/index phù hợp. |
| “E121 là lỗi do Java serializer.” | 121 là lỗi collection validator ở server; serializer có thể có lỗi riêng trước đó. |
| “Có `$jsonSchema` thì mọi invalid document luôn bị từ chối.” | Phụ thuộc `validationAction`, `validationLevel` và bypass được cấp quyền. |
| “Có timeout nghĩa là server không ghi gì.” | Một phần thao tác có thể đã diễn ra mà chưa được xác nhận ở mức yêu cầu. |
| “Retry toàn batch sẽ tự hoàn tất những dòng còn thiếu.” | Có thể tạo thêm lỗi trùng và khó phân biệt kết quả của từng lần chạy. |
| “Chỉ cần bắt exception rồi HTTP 500.” | API import cần báo chính xác phần thành công, phần từ chối, phần chưa thử và phần chưa rõ. |

## 19. Tài liệu MongoDB chính thức

- [Insert Many — mongosh](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/): `ordered`, `unordered`, write errors, write concern và kết quả insert theo lô.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): `_id`, unique compound index, giá trị null/thiếu, duplicate key.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/): validator và cấu trúc document.
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/): `validationAction` và cách xử lý document không hợp lệ.
- [MongoDB Error Codes](https://www.mongodb.com/docs/manual/reference/error-codes/): mã 11000, 121 và các mã lỗi server khác.
- [Java Sync Driver — Insert Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/insert/): `InsertOneResult`, `InsertManyResult`, `MongoWriteException`, `MongoBulkWriteException`.
- [Java Sync Driver — Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/): bulk models, `BulkWriteResult`, `ordered` và xử lý lỗi.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): mức xác nhận và các trường hợp ghi chưa được xác nhận theo yêu cầu.

Cách xử lý đúng một lần ghi MongoDB có lỗi là **phân biệt lỗi từ chối dữ liệu, kết quả ghi đã xác nhận và kết quả chưa rõ**. Unique index giữ ràng buộc duy nhất, validator giữ cấu trúc dữ liệu, còn `ordered` quyết định mức tiếp tục của lô. Ứng dụng phải ghép ba yếu tố đó với **ID ổn định, partial result, transaction khi cần và cơ chế đối soát/retry có kiểm soát** để dữ liệu đúng ngay cả khi có lỗi giữa chừng.
