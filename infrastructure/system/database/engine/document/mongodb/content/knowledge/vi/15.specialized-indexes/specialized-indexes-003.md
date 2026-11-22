# Sparse index và partial index với điều kiện lọc trong MongoDB

## Mục tiêu bài học

Index trong MongoDB giúp truy vấn tìm document nhanh hơn bằng cách lưu cấu trúc dữ liệu được tổ chức theo những trường cần tìm kiếm hoặc sắp xếp. Tuy nhiên, không phải mọi document trong collection đều cần đóng góp một index entry cho một nghiệp vụ nhất định. Khi collection có nhiều document thiếu một field, hoặc ứng dụng chỉ thường truy vấn một nhóm document thỏa điều kiện cụ thể, có thể dùng **sparse index** hoặc **partial index** để giới hạn dữ liệu được đưa vào index.

Hai loại index này thường bị nhầm lẫn:

- **Sparse index** chủ yếu dựa vào việc field được index **có tồn tại hay không**.
- **Partial index** dùng **`partialFilterExpression`** để định nghĩa tập document được index theo điều kiện lọc; điều kiện này có thể dựa trên field được index hoặc field khác.

Điểm khác biệt ảnh hưởng đến nhiều thứ: kích thước index, write overhead, tính duy nhất (unique), khả năng planner chọn index và độ chính xác của truy vấn khi có field thiếu hoặc giá trị `null`.

Sau bài học, người học có thể:

1. Tạo sparse và partial index bằng `createIndex()`.
2. Giải thích chính xác document nào có index entry, đặc biệt với **missing** và **`null`**.
3. Chọn `partialFilterExpression` cho dữ liệu theo trạng thái, loại document hoặc vùng giá trị.
4. Hiểu khi nào partial/sparse index **có thể không được query planner chọn** để tránh bỏ sót document.
5. Kết hợp `unique: true` với sparse/partial và nhận biết rủi ro duplicate key.
6. Đọc định nghĩa index và kiểm tra kế hoạch truy vấn với `getIndexes()` và `explain("executionStats")`.
7. Phân tích chi phí tạo, bảo trì, thay đổi, xóa và migration index.
8. Lựa chọn index theo workload, tính đúng đắn và đặc tính dữ liệu thay vì dựa trên giả định "index nhỏ thì luôn nhanh".

> **Ý chính:** Sparse index là công cụ tương đối đơn giản cho trường **tùy chọn**. Partial index biểu diễn một **tập document có điều kiện** rõ ràng hơn. Cả hai đều cần một query phù hợp với phạm vi dữ liệu của index để không làm kết quả sai hoặc thiếu.

---

## 1. Ôn lại vai trò của index trong MongoDB

Giả sử collection `customers` có hàng triệu document. Khi tìm email:

~~~javascript
db.customers.findOne({
  email: "an@example.test"
});
~~~

Nếu không có index phù hợp, MongoDB có thể phải kiểm tra nhiều document trong collection. Một index thông thường:

~~~javascript
db.customers.createIndex({
  email: 1
});
~~~

cho phép lưu các giá trị `email` theo thứ tự trong cấu trúc index. Trong trường hợp có nhiều document thiếu email, một index đơn trường thông thường vẫn có các entry tương ứng với những document thiếu/null theo quy tắc của MongoDB, dẫn đến công lưu trữ và kiểm tra index có thể không mang nhiều lợi ích cho những truy vấn chỉ tìm khách có email thật.

Với index trên một field, ba tình huống phải tách riêng:

~~~javascript
// Document A: có giá trị email dạng string
{ _id: "A", email: "an@example.test" }

// Document B: field email tồn tại, nhưng giá trị null
{ _id: "B", email: null }

// Document C: hoàn toàn không có field email
{ _id: "C", fullName: "Bình" }
~~~

**Missing** và **`null`** không phải cùng một trạng thái dữ liệu:

- Missing: field không tồn tại trong document.
- `null`: field tồn tại nhưng chứa giá trị BSON null.

Một câu truy vấn:

~~~javascript
db.customers.find({
  email: null
});
~~~

thường khớp cả document có `email: null` lẫn document **thiếu email**. Ngược lại:

~~~javascript
db.customers.find({
  email: { $exists: true }
});
~~~

chọn những document có field email tồn tại, **bao gồm** giá trị null.

Truy vấn:

~~~javascript
db.customers.find({
  email: { $type: "string" }
});
~~~

giới hạn về những document có giá trị email phù hợp kiểu string. Sự khác nhau này là nền tảng để thiết kế sparse và partial index.

### 1.1. Một index tác động đến cả đọc lẫn ghi

Index có lợi cho nhiều read patterns, nhưng phải trả chi phí:

- Tốn dung lượng lưu cấu trúc index.
- Tốn bộ nhớ/cache khi index được dùng.
- Insert phải thêm index entry nếu document thuộc phạm vi index.
- Update có thể thêm, xóa hoặc đổi key trong index.
- Delete phải cập nhật index tương ứng.
- Index build trên collection lớn có thể tốn tài nguyên.
- Unique index áp đặt ràng buộc và có thể làm ghi thất bại khi trùng khóa.

Sparse và partial index giúp giảm một số chi phí nếu phạm vi được chọn hợp lý. Nhưng index quá hẹp có thể **không phục vụ được các query cần toàn bộ document**.

### 1.2. Câu hỏi thiết kế phải đặt trước

Trước khi dùng sparse/partial:

1. Field có thể thiếu hay chỉ có thể null?
2. Query thường lọc theo những điều kiện nào?
3. Document nào cần **được tìm thấy**, document nào không nằm trong phạm vi truy vấn?
4. Có cần unique chỉ với một tập con document không?
5. Tập con đó có thay đổi thường xuyên không?
6. Query sort, pagination hoặc aggregation có cần cả document ngoài tập con không?
7. Index hiện tại có đang phục vụ những endpoint khác không?

**Không chọn index chỉ vì nó có kích thước nhỏ hơn**. Cần chứng minh index phục vụ đúng workload.

---

## 2. Sparse index là gì?

Một sparse index chỉ bao gồm những document có field được index **tồn tại**, ngay cả khi giá trị field đó là `null`. Với **single-field sparse index** trên `email`:

~~~javascript
db.customers.createIndex(
  { email: 1 },
  { sparse: true }
);
~~~

MongoDB bỏ qua những document không có field `email` khi tạo index này.

Ví dụ:

| Document | `email` | Có entry trong sparse index `{email:1}`? |
|---|---|---|
| A | `"an@example.test"` | **Có** |
| B | `null` | **Có** |
| C | Missing | **Không** |
| D | `""` (chuỗi rỗng) | **Có** |
| E | `123` (number, nếu schema cho phép) | **Có** |

**Chốt quan trọng:** Sparse **không** có nghĩa “chỉ index giá trị khác null”. Nó kiểm tra **sự hiện diện** của field, không mặc định loại giá trị null hoặc chuỗi rỗng.

### 2.1. Ví dụ thực tế

Collection `profiles` chứa những tài khoản có hoặc chưa có số điện thoại:

~~~javascript
db.profiles.insertMany([
  {
    _id: "U-101",
    displayName: "An",
    phone: "0901000001"
  },
  {
    _id: "U-102",
    displayName: "Bình"
  },
  {
    _id: "U-103",
    displayName: "Chi",
    phone: null
  },
  {
    _id: "U-104",
    displayName: "Dung",
    phone: "0901000004"
  }
]);
~~~

Tạo sparse index:

~~~javascript
db.profiles.createIndex(
  { phone: 1 },
  {
    sparse: true,
    name: "idx_profiles_phone_sparse"
  }
);
~~~

Index có entry cho U-101, U-103 và U-104, nhưng bỏ qua U-102 vì U-102 thiếu `phone`.

Truy vấn thông thường:

~~~javascript
db.profiles.find({
  phone: "0901000001"
});
~~~

có thể tận dụng index vì document khớp chắc chắn có field phone.

Tuy nhiên, truy vấn tìm mọi profile:

~~~javascript
db.profiles.find({}).sort({
  phone: 1
});
~~~

**không thể chỉ dựa vào sparse index mà vẫn bảo đảm đầy đủ kết quả**, vì U-102 không hề nằm trong index. Trong tình huống như vậy, query planner có thể chọn đường thực thi khác để không bỏ sót document.

### 2.2. Kiểm tra định nghĩa index

~~~javascript
db.profiles.getIndexes();
~~~

Một định nghĩa có dạng tương tự:

~~~javascript
{
  v: 2,
  key: { phone: 1 },
  name: "idx_profiles_phone_sparse",
  sparse: true
}
~~~

Các metadata như `v` có thể khác theo phiên bản. Điều cần kiểm tra là `key` và option `sparse: true`.

### 2.3. Không nên hiểu sparse index là bảo đảm query luôn dùng index

MongoDB query planner cần bảo đảm truy vấn không thiếu kết quả. Nó thường không chọn sparse index khi sử dụng index sẽ bỏ sót document phù hợp filter.

Ví dụ:

~~~javascript
db.profiles.find({
  phone: null
});
~~~

Truy vấn này có thể khớp **cả document thiếu phone**. Sparse index không có U-102, nên sử dụng index như nguồn duy nhất có thể trả thiếu dữ liệu. Không nên kỳ vọng planner tự chọn index trong trường hợp này.

Ngược lại:

~~~javascript
db.profiles.find({
  phone: { $exists: true }
});
~~~

chỉ cần các document có `phone`, do đó phạm vi tương thích với sparse index. Nhưng việc planner có thực sự chọn index nào vẫn phụ thuộc filter, sort, kích thước dữ liệu và chi phí ước lượng.

---

## 3. Sparse index với nhiều field và các giới hạn

### 3.1. Compound sparse index không đơn giản là "mọi field đều tồn tại"

Với compound sparse index chỉ gồm các khóa ascending/descending, MongoDB có thể tạo entry cho document nếu **ít nhất một trong các field được index tồn tại**.

Ví dụ:

~~~javascript
db.contacts.createIndex(
  {
    email: 1,
    phone: 1
  },
  {
    sparse: true,
    name: "idx_contacts_email_phone_sparse"
  }
);
~~~

Các document:

~~~javascript
{ _id: 1, email: "a@example.test" }
{ _id: 2, phone: "0900000002" }
{ _id: 3, email: "c@example.test", phone: "0900000003" }
{ _id: 4, displayName: "Không có liên hệ" }
~~~

Ở dạng compound index thông thường gồm hai khóa `email` và `phone`:

- Document 1 có entry vì email tồn tại.
- Document 2 có entry vì phone tồn tại.
- Document 3 có entry vì cả hai tồn tại.
- Document 4 không có entry vì cả hai đều vắng.

Đừng hiểu rằng compound sparse chỉ nhận document có **đủ cả email và phone**.

**Lưu ý đặc biệt:** Compound index chứa text hoặc 2dsphere keys có các quy tắc sparse riêng và phụ thuộc loại key. Khi sử dụng những loại index đó, cần đọc phần tài liệu về compound sparse indexes của đúng phiên bản. Quy tắc "ít nhất một field tồn tại" trong ví dụ trên áp dụng cho tổ hợp khóa tăng/giảm thông thường.

### 3.2. Vì sao compound sparse có thể gây ngạc nhiên?

Giả sử hệ thống muốn uniqueness trên cặp email–phone, nhưng một số document chỉ có email. Compound sparse index có thể vẫn index chúng. Khi kết hợp `unique: true`, các giá trị thiếu ở từng thành phần compound key được xử lý theo quy tắc uniqueness của MongoDB, có thể gây duplicate key ở các trường hợp ít được dự đoán trước.

Nếu điều kiện nghiệp vụ là "chỉ index document mà cả email và phone đều tồn tại", sparse không biểu diễn chính xác yêu cầu này. Một partial index với điều kiện tồn tại trên cả hai field sẽ minh bạch hơn:

~~~javascript
db.contacts.createIndex(
  { email: 1, phone: 1 },
  {
    partialFilterExpression: {
      email: { $exists: true },
      phone: { $exists: true }
    },
    name: "idx_contacts_both_fields"
  }
);
~~~

Lưu ý rằng `$exists: true` vẫn bao gồm giá trị null. Nếu nghiệp vụ yêu cầu chuỗi thực, dùng điều kiện theo kiểu BSON phù hợp thay vì chỉ kiểm tra tồn tại.

### 3.3. Sparse và các loại index đặc biệt

Không thể suy ra mọi đặc tính của sparse index đơn trường thường sang text, wildcard, geospatial hoặc các index dạng đặc biệt. Chẳng hạn một số loại index có hành vi sparse vốn có; một số có điều kiện tạo entry riêng.

Khi bài toán thực chất là tìm kiếm toàn văn, truy vấn tọa độ hoặc wildcard fields, hãy thiết kế theo đặc tính của loại index đó, không mặc định dùng `sparse: true` sẽ có hiệu quả như một B-tree index đơn trường.

---

## 4. Unique sparse index và field tùy chọn

### 4.1. Nhiều document thiếu field có thể cùng tồn tại

Giả sử ứng dụng cho phép tài khoản **chưa cung cấp email**, nhưng khi đã cung cấp thì email không được trùng.

~~~javascript
db.members.createIndex(
  { email: 1 },
  {
    sparse: true,
    unique: true,
    name: "uk_members_email_sparse"
  }
);
~~~

Ví dụ:

~~~javascript
db.members.insertMany([
  { _id: "M-001", name: "An" },
  { _id: "M-002", name: "Bình" },
  {
    _id: "M-003",
    name: "Chi",
    email: "chi@example.test"
  }
]);
~~~

Hai document M-001 và M-002 đều thiếu email; không có entry `email` tương ứng trong index sparse, nên việc cùng thiếu email không gây xung đột uniqueness của index này.

Nhưng insert:

~~~javascript
db.members.insertOne({
  _id: "M-004",
  name: "Dung",
  email: "chi@example.test"
});
~~~

bị từ chối vì trùng email với M-003, thường có duplicate key error code **11000**.

### 4.2. Nhiều giá trị null vẫn là vấn đề

Sparse index **có index** document mà `email: null`. Với một **unique sparse index đơn trường**, chỉ một document có thể mang khóa null tương ứng, trong những điều kiện unique thông thường.

Ví dụ:

~~~javascript
db.members.insertOne({
  _id: "M-005",
  name: "Hà",
  email: null
});
~~~

Sau đó:

~~~javascript
db.members.insertOne({
  _id: "M-006",
  name: "Lan",
  email: null
});
~~~

Lệnh thứ hai có thể bị duplicate key do hai document cùng có field email và cùng giá trị null.

Đây là khác biệt rất quan trọng:

| Trạng thái email | `unique: true, sparse: true` |
|---|---|
| Thiếu email | Không tạo index entry, nhiều document có thể thiếu |
| Email có string duy nhất | Hợp lệ |
| Hai email string giống nhau | Duplicate key |
| Email bằng null | **Được index**, nên nhiều null có thể xung đột |
| Email là chuỗi rỗng | Có index entry, nhiều chuỗi rỗng có thể xung đột |

Nếu hệ thống lưu "chưa cung cấp email" dưới dạng `null`, unique sparse thường **không giải quyết đúng yêu cầu** "cho phép nhiều user chưa có email".

### 4.3. Khi nào unique sparse phù hợp?

Unique sparse là lựa chọn đơn giản khi ứng dụng thống nhất:

- Người chưa có email **không lưu field email**.
- Người đã có email lưu một giá trị hợp lệ.
- Dữ liệu không có nhiều email null.
- Muốn uniqueness trên mọi giá trị email có mặt.

Nếu dữ liệu hiện có chứa rất nhiều null, không nên chỉ bật unique sparse rồi mong index build thành công. Cần migration dữ liệu hoặc chọn partial index có bộ lọc hợp lý.

---

## 5. Partial index: chỉ index document thỏa điều kiện lọc

### 5.1. Khái niệm

**Partial index** xác định tập document được index bằng option `partialFilterExpression`.

Ví dụ chỉ index khách đang hoạt động:

~~~javascript
db.customers.createIndex(
  { lastLoginAt: -1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_customers_last_login"
  }
);
~~~

Định nghĩa này có hai phần:

1. **Index key:** `{ lastLoginAt: -1 }` — dữ liệu dùng để tìm/sắp xếp.
2. **Filter expression:** `{ status: "ACTIVE" }` — **chỉ document ACTIVE** được đưa vào index.

**Điểm mạnh:** Field điều kiện lọc **không bắt buộc trùng** field làm index key. Đây là khác biệt lớn so với sparse đơn trường: partial index có thể xây trên `lastLoginAt` nhưng chỉ lưu document có `status: "ACTIVE"`.

### 5.2. Ví dụ theo trạng thái

~~~javascript
db.customers.insertMany([
  {
    _id: "C-101",
    status: "ACTIVE",
    lastLoginAt: ISODate("2026-11-10T08:00:00Z")
  },
  {
    _id: "C-102",
    status: "INACTIVE",
    lastLoginAt: ISODate("2026-11-12T08:00:00Z")
  },
  {
    _id: "C-103",
    status: "ACTIVE",
    lastLoginAt: ISODate("2026-11-13T08:00:00Z")
  },
  {
    _id: "C-104",
    status: "DELETED",
    lastLoginAt: ISODate("2026-11-14T08:00:00Z")
  }
]);
~~~

Index:

~~~javascript
db.customers.createIndex(
  { lastLoginAt: -1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_last_login"
  }
);
~~~

Index này bao gồm các document C-101 và C-103, nhưng không bao gồm C-102 và C-104.

Query phù hợp:

~~~javascript
db.customers.find({
  status: "ACTIVE"
}).sort({
  lastLoginAt: -1
});
~~~

Vì query **chỉ yêu cầu document ACTIVE**, phạm vi của query nằm trong phần dữ liệu được index. Planner có thể xem xét partial index để tránh duyệt mọi document còn lại.

### 5.3. Filter không phải là điều kiện áp dụng tự động vào query

Partial index không có nghĩa MongoDB sẽ "tự thêm `status: 'ACTIVE'`" cho mọi truy vấn dùng `lastLoginAt`.

Ví dụ:

~~~javascript
db.customers.find({}).sort({
  lastLoginAt: -1
});
~~~

Query này yêu cầu **cả ACTIVE, INACTIVE và DELETED**, trong khi partial index chỉ có ACTIVE. Nếu planner dùng partial index làm nguồn kết quả duy nhất, sẽ mất document. Bởi vậy planner thông thường **không chọn partial index cho truy vấn có thể cần document ngoài bộ lọc**.

Cần luôn phân biệt:

~~~text
partialFilterExpression = điều kiện để document thuộc index.

query filter = điều kiện người dùng muốn tìm.

Muốn query dùng index an toàn:
  Phạm vi kết quả query phải phù hợp
  với tập document đã được index.
~~~

---

## 6. Các điều kiện dùng trong partialFilterExpression

MongoDB hỗ trợ một tập các toán tử nhất định trong `partialFilterExpression`. Những loại thường gặp:

| Biểu thức | Ý nghĩa | Ví dụ |
|---|---|---|
| Equality | Field bằng giá trị cụ thể | `{ status: "ACTIVE" }` |
| `$exists: true` | Field tồn tại | `{ email: { $exists: true } }` |
| Range | So sánh `$gt`, `$gte`, `$lt`, `$lte` | `{ score: { $gte: 80 } }` |
| `$type` | Kiểm tra kiểu BSON | `{ email: { $type: "string" } }` |
| `$in` | Field thuộc nhóm giá trị | `{ status: { $in: ["NEW", "ACTIVE"] } }` |
| `$and` / `$or` | Kết hợp các điều kiện được hỗ trợ | Xem ví dụ dưới |

Khả năng hỗ trợ expression có thay đổi theo phiên bản, nên khi triển khai phải kiểm tra tài liệu của server hiện tại. Không phải mọi query operator đều hợp lệ trong `partialFilterExpression`. Đặc biệt, không nên mặc định dùng `$ne`, `$regex`, `$expr` hay `$exists: false` như những option tạo partial index được hỗ trợ.

### 6.1. Filter nhiều điều kiện

Ví dụ chỉ index các ticket đang mở và có mức ưu tiên cao:

~~~javascript
db.tickets.createIndex(
  { updatedAt: -1, _id: -1 },
  {
    partialFilterExpression: {
      status: "OPEN",
      priority: { $gte: 4 }
    },
    name: "idx_open_high_priority_recent"
  }
);
~~~

Document chỉ được đưa vào index nếu **cả hai** điều kiện được đáp ứng:

~~~text
status = OPEN
AND
priority >= 4
~~~

Query phù hợp:

~~~javascript
db.tickets.find({
  status: "OPEN",
  priority: { $gte: 4 }
}).sort({
  updatedAt: -1,
  _id: -1
}).limit(20);
~~~

Một query hẹp hơn cũng có thể đủ điều kiện:

~~~javascript
db.tickets.find({
  status: "OPEN",
  priority: { $gte: 5 }
}).sort({
  updatedAt: -1,
  _id: -1
}).limit(20);
~~~

Vì `priority >= 5` là tập con của `priority >= 4`, mọi document query cần đều thỏa partial filter. Planner có thể chọn index nếu chi phí phù hợp.

Ngược lại:

~~~javascript
db.tickets.find({
  status: "OPEN",
  priority: { $gte: 2 }
});
~~~

có thể yêu cầu các ticket priority 2 hoặc 3 **không được index**, nên partial index không đủ để trả toàn bộ kết quả của query.

### 6.2. Filter theo loại document

Một collection có nhiều loại tài liệu:

~~~javascript
{
  _id: "DOC-001",
  docType: "INVOICE",
  invoiceNo: "INV-101"
}

{
  _id: "DOC-002",
  docType: "RECEIPT",
  receiptNo: "RCPT-301"
}
~~~

Nếu chỉ invoice có `invoiceNo`, có thể tạo:

~~~javascript
db.documents.createIndex(
  { invoiceNo: 1 },
  {
    partialFilterExpression: {
      docType: "INVOICE"
    },
    name: "idx_invoice_no_for_invoices"
  }
);
~~~

Query:

~~~javascript
db.documents.find({
  docType: "INVOICE",
  invoiceNo: "INV-101"
});
~~~

Nếu query chỉ có `invoiceNo` mà **không** khẳng định `docType`, planner không mặc nhiên biết rằng ngoài invoice không bao giờ có field này, trừ khi nó có thể chứng minh điều đó từ predicate và các quy tắc được hỗ trợ. Vì vậy, khi thiết kế API, nên nêu rõ các điều kiện phân loại phù hợp trong query.

### 6.3. Filter theo sự tồn tại và kiểu dữ liệu

Để index mọi document có field `email`:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    partialFilterExpression: {
      email: { $exists: true }
    },
    name: "idx_accounts_existing_email"
  }
);
~~~

Index này có thể phục vụ một mục đích tương tự sparse đơn trường, **vẫn bao gồm null**.

Nếu chỉ muốn các email thực sự là chuỗi:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "idx_accounts_string_email"
  }
);
~~~

Điều kiện `$type: "string"` hữu ích khi dữ liệu có các kiểu field khác nhau. Tuy nhiên, MongoDB query/aggregation có quy tắc riêng với array và `$type`; với một hệ thống yêu cầu email luôn là scalar string, **schema validation** là lớp bảo vệ cần thiết. Đừng chỉ dựa vào partial filter để chống dữ liệu sai kiểu.

---

## 7. Partial unique index: uniqueness chỉ trong tập con

### 7.1. Uniqueness theo trạng thái

Giả sử ứng dụng cho phép nhiều bản ghi lịch sử có cùng `username` nhưng chỉ một bản ghi **ACTIVE** cho mỗi username.

~~~javascript
db.user_records.createIndex(
  { username: 1 },
  {
    unique: true,
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "uk_active_username"
  }
);
~~~

Ý nghĩa:

- Hai document có `username: "an"` và status INACTIVE có thể cùng tồn tại.
- Một document có username `"an"` và status ACTIVE có thể tồn tại.
- Insert hoặc update thêm một document khác cũng ACTIVE với username `"an"` sẽ vi phạm unique index.

Ví dụ:

~~~javascript
db.user_records.insertMany([
  {
    _id: "U-001",
    username: "an",
    status: "INACTIVE"
  },
  {
    _id: "U-002",
    username: "an",
    status: "DELETED"
  },
  {
    _id: "U-003",
    username: "an",
    status: "ACTIVE"
  }
]);
~~~

Nhưng:

~~~javascript
db.user_records.insertOne({
  _id: "U-004",
  username: "an",
  status: "ACTIVE"
});
~~~

có thể nhận duplicate key error 11000.

Điểm quan trọng: uniqueness **chỉ được áp dụng cho các document thỏa `partialFilterExpression`**, không phải toàn collection.

### 7.2. Chuyển trạng thái có thể tạo duplicate key

Giả sử document INACTIVE có username trùng document ACTIVE. Nếu update:

~~~javascript
db.user_records.updateOne(
  { _id: "U-001" },
  {
    $set: {
      status: "ACTIVE"
    }
  }
);
~~~

thao tác này có thể thất bại do document U-001 nay đi vào phạm vi index và trùng unique key của U-003.

Partial unique index không chỉ kiểm soát **insert**, mà cả update khiến document:

- Đi từ **ngoài** vào **trong** tập con.
- Thay đổi giá trị field indexed khi vẫn nằm **trong** tập con.
- Đi từ **trong** ra **ngoài** tập con.

Các thay đổi trạng thái có thể thêm hoặc xóa index entry, nên cần tính vào chi phí ghi.

### 7.3. Unique email chỉ khi email là string

Nếu muốn nhiều tài khoản chưa có email **hoặc email null**, nhưng email dạng string không được trùng:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "uk_accounts_string_email"
  }
);
~~~

Với yêu cầu và kiểu field thông thường:

| Email | Có entry trong partial unique index? |
|---|---|
| Missing | Không |
| `null` | Không |
| `"an@example.test"` | Có |
| `"binh@example.test"` | Có |
| `""` | Có, vì chuỗi rỗng vẫn là string |
| `123` | Không, nếu không thỏa kiểu string theo query semantics |

Lưu ý:

- Đây là **quy tắc index**, không phải validator hoàn chỉnh của email.
- `""` vẫn là string; nếu ứng dụng không cho phép email rỗng, phải kiểm tra ở application hoặc schema validator.
- Nếu email dạng array hoặc dữ liệu có kiểu bất thường, cần kiểm tra semantics của `$type` và multikey index thay vì áp dụng bảng scalar trên một cách máy móc.
- Nếu email không phân biệt hoa/thường, cần xét **collation**, chuẩn hóa dữ liệu và unique semantics. Chỉ tạo partial index không tự tạo case-insensitive uniqueness.

### 7.4. Unique partial không đồng nghĩa mọi document unique

Ví dụ unique index có filter:

~~~javascript
partialFilterExpression: {
  status: "ACTIVE"
}
~~~

thì các document INACTIVE có thể trùng username. Điều này hoàn toàn đúng với index, nhưng không phù hợp nếu nghiệp vụ yêu cầu username unique **vĩnh viễn** kể cả sau khi tài khoản bị khóa. Phải chọn filter theo **hợp đồng dữ liệu**, không chỉ theo cách tối ưu dung lượng.

---

## 8. So sánh sparse index và partial index

| Tiêu chí | Sparse index | Partial index |
|---|---|---|
| Tùy chọn | `sparse: true` | `partialFilterExpression: {...}` |
| Ý tưởng chính | Loại document thiếu field indexed | Chỉ index document thỏa predicate |
| Kiểm tra null ở index đơn trường | `null` vẫn được index nếu field tồn tại | Tùy filter; có thể loại null với `$type` |
| Filter trên field khác | Không phải thế mạnh của sparse | **Có**, như index `lastLoginAt` chỉ khi `status=ACTIVE` |
| Điều kiện range | Không diễn đạt trực tiếp | Có thể dùng range operators được hỗ trợ |
| Unique theo tập con | Nhiều missing có thể tồn tại; null vẫn có thể trùng | Unique chỉ trong các document thỏa filter |
| Compound keys | Có quy tắc sparse riêng | Phạm vi do predicate quyết định |
| Khả năng query planner dùng | Cần đủ dữ liệu để trả đầy đủ query | Query phải thỏa/bao hàm được điều kiện index |
| Chi phí index | Ít entry nếu nhiều document thiếu field | Ít entry nếu predicate chọn tập con nhỏ |
| Thiết kế mới | Hợp lý với trường tùy chọn đơn giản | Thường linh hoạt hơn với yêu cầu lọc cụ thể |

### 8.1. Sparse có thể xem như một trường hợp gần partial

Với một field scalar thông thường, hai index:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    name: "idx_sparse_email"
  }
);
~~~

và:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    partialFilterExpression: {
      email: { $exists: true }
    },
    name: "idx_partial_existing_email"
  }
);
~~~

có mục tiêu chọn document tương tự nhau. Nhưng không nên suy ra rằng chúng giống hoàn toàn trong mọi kiểu compound index hoặc loại index chuyên biệt.

**MongoDB không cho khai báo đồng thời `sparse` và `partialFilterExpression` trong cùng một định nghĩa index.** Khi muốn biểu diễn điều kiện phức tạp, chọn partial index thay vì cố kết hợp hai options.

### 8.2. Tại sao partial linh hoạt hơn?

Giả sử ứng dụng chỉ đọc các đơn đang mở:

~~~javascript
db.orders.find({
  status: "OPEN",
  customerId: "C-101"
}).sort({
  createdAt: -1
});
~~~

Có thể tạo:

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1
  },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_orders_customer_created"
  }
);
~~~

Index key không cần lưu `status` chỉ để giới hạn tập document; điều kiện index đã loại toàn bộ đơn CLOSED/CANCELED khỏi index. Điều này có thể giảm kích thước và công ghi cho workload chỉ quan tâm OPEN.

Đổi lại, nếu ứng dụng còn cần query lịch sử CLOSED theo khách, index này **không đủ phục vụ**. Có thể cần index khác cho đường đọc lịch sử.

---

## 9. Query planner chỉ được chọn index khi không làm thiếu kết quả

Đây là phần quan trọng nhất khi dùng partial/sparse index.

### 9.1. Quy tắc tập con

Giả sử partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      total: { $gte: 1000000 }
    },
    name: "idx_large_orders_created"
  }
);
~~~

Index chứa order có `total >= 1000000`.

Một query:

~~~javascript
db.orders.find({
  total: { $gte: 2000000 }
}).sort({
  createdAt: -1
});
~~~

chỉ cần các order có total ít nhất 2 triệu; tất cả đều nằm trong index vì `2 triệu >= 1 triệu`. Planner có thể dùng index.

Query:

~~~javascript
db.orders.find({
  total: { $gte: 500000 }
});
~~~

yêu cầu những order từ 500 nghìn đến dưới 1 triệu **không có trong partial index**. Planner không thể dùng index này như nguồn duy nhất nếu muốn trả đầy đủ kết quả.

Cách tư duy:

~~~text
Index predicate:
  P(document) = total >= 1000000

Query predicate:
  Q(document) = total >= 2000000

Nếu mọi Q đều thỏa P:
  Query có thể dùng index mà không bỏ sót kết quả.

Nếu tồn tại Q không thỏa P:
  Index không đủ để trả đầy đủ query.
~~~

Đây là quy tắc về **tính đúng đắn của tập kết quả**, trước khi nói đến performance.

### 9.2. Query phải thể hiện điều kiện tương thích

Partial index:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_created"
  }
);
~~~

Query phù hợp:

~~~javascript
db.orders.find({
  status: "OPEN"
}).sort({
  createdAt: -1
});
~~~

Query không phù hợp:

~~~javascript
db.orders.find({}).sort({
  createdAt: -1
});
~~~

Query thứ hai cần mọi status. Planner thường không chọn index chỉ chứa OPEN.

Với những query có filter phức tạp, `$or`, `$in`, type coercion hoặc collation, khả năng planner **chứng minh tương thích** là một chi tiết quan trọng. Không nên viết filter nghiệp vụ mơ hồ và kỳ vọng optimizer tự suy luận mọi ràng buộc từ ứng dụng.

### 9.3. Dùng `hint()` cần đặc biệt cẩn thận

Có thể ép query dùng một index bằng `hint()`, ví dụ:

~~~javascript
db.orders.find({}).hint(
  "idx_open_created"
);
~~~

Nếu chỉ dùng partial index chứa OPEN để trả một query yêu cầu **mọi document**, kết quả có thể **không đầy đủ**. Tương tự, ép sparse index trên query cần document thiếu field có thể bỏ sót dữ liệu.

Không dùng `hint` để "ép query chạy nhanh" khi chưa chứng minh tập kết quả vẫn đúng. Query planner thường cố tránh những index khiến kết quả thiếu; ép index có thể vượt qua sự bảo vệ đó trong những trường hợp nhất định.

### 9.4. Sắp xếp cũng cần dữ liệu đầy đủ

Ví dụ:

~~~javascript
db.customers.find({}).sort({
  lastLoginAt: -1
});
~~~

Nếu partial index chỉ có status ACTIVE, việc lấy dữ liệu theo thứ tự index không đủ trả những khách INACTIVE có `lastLoginAt`. Planner phải chọn một cách khác hoặc sử dụng cấu trúc đáp ứng query.

Không kết luận index hiệu quả chỉ vì `sort` trùng hướng của key index; **phạm vi dữ liệu** cũng phải phù hợp.

---

## 10. Kiểm tra index bằng explain

### 10.1. Chuẩn bị index

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_by_customer"
  }
);
~~~

### 10.2. Query phù hợp

~~~javascript
const plan = db.orders
  .find({
    customerId: "C-101",
    status: "OPEN"
  })
  .sort({
    createdAt: -1,
    _id: -1
  })
  .limit(20)
  .explain("executionStats");

printjson(plan.queryPlanner.winningPlan);
printjson(plan.executionStats);
~~~

Những thông tin đáng xem:

| Trường | Ý nghĩa |
|---|---|
| `winningPlan` | Kế hoạch truy vấn được chọn |
| `IXSCAN` / hình thức index scan tương ứng | Duyệt index |
| `COLLSCAN` | Quét collection |
| `SORT` hoặc bước sort tương đương | Có bước sort riêng |
| `nReturned` | Số document trả ra |
| `totalKeysExamined` | Số index entry được duyệt |
| `totalDocsExamined` | Số document được đọc/kiểm tra |
| `executionTimeMillis` | Thời gian theo kết quả explain |

Hình dạng plan có thể khác tùy MongoDB version/query engine; có thể cần đọc các nhánh bên trong winning plan. Một query nhỏ có thể được planner chọn COLLSCAN vì rẻ hơn ngay cả khi index hợp lệ; không lấy một bộ dữ liệu vài document làm kết luận index vô ích.

### 10.3. Query không chứa partial filter

~~~javascript
db.orders
  .find({ customerId: "C-101" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Query này cần cả OPEN và CLOSED. Partial index chỉ chứa OPEN **không đủ**. So sánh kế hoạch và lý giải vì sao planner có thể chọn index khác hoặc collection scan.

### 10.4. Kết quả explain không thay benchmark

`explain("executionStats")` giúp đọc chiến lược thực thi và lượng công index/document scan. Nhưng latency API còn gồm connection pool, mạng, BSON decoding, mapping Java object, serialization, caching, concurrency và write load.

Benchmark cần:

- Số liệu thực/giả lập đại diện.
- Query có chọn lọc và query ít chọn lọc.
- Cùng hạ tầng và MongoDB version.
- Cùng index khác và write concern khi so sánh.
- Warm-up, nhiều lượt đo, p95/p99 latency.
- Trạng thái cache và phân bố dữ liệu thực tế.

---

## 11. Đánh giá dung lượng và chi phí duy trì index

### 11.1. Sparse/partial có thể làm index nhỏ hơn

Giả sử collection có 2 triệu user:

- 1,6 triệu user chưa có số điện thoại.
- 400 nghìn user có số điện thoại.
- Phần lớn query theo số điện thoại chỉ tìm giá trị cụ thể.

Một sparse index trên `phone` có thể chỉ lưu entry cho khoảng 400 nghìn document có phone, thay vì tạo entry cho cả các document thiếu field. Nhưng nếu nhiều document có `phone: null`, chúng **vẫn thuộc sparse index** và con số sẽ lớn hơn.

Nếu nghiệp vụ chỉ dùng phone dạng string, partial index với `$type: "string"` có thể loại thêm các giá trị null khỏi phạm vi index.

**Không đồng nhất số index entry với số byte trên disk.** Dung lượng thực tế còn phụ thuộc key size, record identifiers, storage engine và compression.

### 11.2. Đo dung lượng

~~~javascript
db.users.stats();
~~~

Kết quả thống kê có thể gồm `indexSizes` và `totalIndexSize`, chẳng hạn:

~~~javascript
{
  indexSizes: {
    "_id_": 123456,
    "idx_phone_sparse": 654321
  },
  totalIndexSize: 777777
}
~~~

Con số ở đây chỉ minh họa. Dữ liệu trên server thật quyết định dung lượng.

Để xem định nghĩa index:

~~~javascript
db.users.getIndexes();
~~~

Để xem thống kê truy cập:

~~~javascript
db.users.aggregate([
  { $indexStats: {} }
]);
~~~

`$indexStats` không phải bằng chứng duy nhất về nhu cầu index. Counter truy cập có thể reset do restart hoặc các thao tác vận hành, và một unique index ít được query vẫn có giá trị bảo đảm ràng buộc dữ liệu.

### 11.3. Một partial index có thể tăng công ghi khi document đổi trạng thái

Partial index `status: "OPEN"` chỉ lưu những order OPEN:

~~~text
Tạo order OPEN:
  -> thêm index entry.

Đổi OPEN -> CLOSED:
  -> loại entry khỏi partial index.

Đổi CLOSED -> OPEN:
  -> thêm entry vào partial index.

Cập nhật createdAt khi vẫn OPEN:
  -> cập nhật key liên quan.
~~~

Nếu status thay đổi cực thường xuyên, chi phí index maintenance có thể đáng kể, dù index chỉ chứa một phần tập dữ liệu. Cần xét **read/write mix** chứ không chỉ dung lượng index hiện tại.

### 11.4. Partial filter không nên quá rộng hoặc quá hẹp

Nếu partial filter chọn 99,9% collection, index có thể không giảm nhiều chi phí so với index thông thường.

Nếu partial filter chọn 0,1% collection nhưng API chủ yếu query những document bên ngoài, index nhỏ nhưng không có ích cho đường đọc chính.

Cần trả lời:

- Tỷ lệ document thỏa filter hiện tại?
- Tỷ lệ này thay đổi thế nào theo thời gian?
- Bao nhiêu phần trăm read queries yêu cầu tập con đó?
- Những operations nào khiến document ra/vào tập con?
- Có query khác vẫn cần full index không?

---

## 12. Unique index, collation và chuẩn hóa dữ liệu

### 12.1. Email không phân biệt hoa/thường

Giả sử ứng dụng xem `An@Example.Test` và `an@example.test` là cùng email. Một unique partial index chỉ dùng:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

không tự bảo đảm case-insensitive comparison theo yêu cầu nghiệp vụ nếu collation mặc định là simple.

Có thể cân nhắc một unique partial index với collation thích hợp:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    collation: {
      locale: "en",
      strength: 2
    },
    name: "uk_accounts_email_case_insensitive"
  }
);
~~~

Lưu ý collation ảnh hưởng đến việc so sánh string và khả năng index được dùng trong query. Cần kiểm tra cách xử lý Unicode, chuẩn hóa email và yêu cầu riêng của hệ thống; không mặc định mọi email được xử lý chính xác bằng lowercase toàn chuỗi trong mọi trường hợp quốc tế.

### 12.2. Null, empty string và missing là ba trạng thái khác

| Dữ liệu | Ý nghĩa có thể có trong nghiệp vụ | Một partial filter `$type:"string"` |
|---|---|---|
| Missing | Chưa cung cấp | Không |
| `null` | Không có giá trị | Không |
| `""` | Chuỗi rỗng | Có |
| `"abc"` | Giá trị chuỗi | Có |

Nếu hệ thống không chấp nhận chuỗi rỗng, hãy dùng schema validation hoặc chuẩn hóa thành missing/null theo một chính sách thống nhất. Không dùng unique index để thay thế validator.

### 12.3. Index có thể không xây được do dữ liệu trùng

Trước khi tạo unique partial index, cần kiểm tra những khóa trùng **trong tập document thỏa filter**.

Ví dụ chỉ kiểm tra user ACTIVE:

~~~javascript
db.user_records.aggregate([
  {
    $match: {
      status: "ACTIVE"
    }
  },
  {
    $group: {
      _id: "$username",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  {
    $match: {
      count: { $gt: 1 }
    }
  }
]);
~~~

Nếu có duplicate username trong tập ACTIVE, unique index có thể không được tạo thành công. Với dữ liệu lớn, aggregation trên có thể tốn tài nguyên và `ids` có thể phình; trong production cần cách kiểm tra/batch phù hợp.

Trước khi áp đặt uniqueness, chốt chính sách xử lý dữ liệu trùng thay vì xóa hoặc đổi tên ngẫu nhiên.

---

## 13. Sparse/partial index không phải công cụ thay schema validation

Một partial index với:

~~~javascript
partialFilterExpression: {
  email: { $type: "string" }
}
~~~

chỉ xác định document nào được index. Nó **không từ chối** document có email là number, null hoặc array nếu collection không có ràng buộc khác.

Ví dụ:

~~~javascript
db.accounts.insertOne({
  _id: "A-100",
  email: 12345
});
~~~

Nếu không có validator hoặc quy tắc application chặn, MongoDB vẫn có thể nhận document này. Nó chỉ có thể không thuộc partial index theo predicate đã chọn.

Nếu yêu cầu nghiệp vụ là “email, khi có, phải là string hợp lệ”, cần dùng:

- Validation trong API/ứng dụng.
- Schema validation ở MongoDB khi phù hợp.
- Unique/partial index để bảo đảm uniqueness trong phạm vi định nghĩa.
- Quy trình chuẩn hóa dữ liệu legacy.

Index và validator giải quyết **hai trách nhiệm khác nhau**:

~~~text
Schema validation:
  Document có cấu trúc/kiểu đúng không?

Unique index:
  Những key trong phạm vi index có bị trùng không?

Partial/sparse index:
  Document nào đóng góp key vào index?

Query planner:
  Index nào có thể dùng mà không thiếu kết quả?
~~~

---

## 14. Phạm vi và hạn chế quan trọng

### 14.1. Không kết hợp sparse với partial trên cùng index

Không khai báo:

~~~javascript
// Không phải cấu hình hợp lệ: chọn một cơ chế.
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

Nếu cần chỉ index email string, dùng partial. Nếu chỉ cần field có tồn tại, sparse đơn trường có thể đủ.

### 14.2. Không áp dụng tùy ý partial lên mọi loại index

MongoDB có các hạn chế theo loại index. Ví dụ, `_id` index không phải đối tượng tùy ý để chuyển thành partial index; shard key index cũng có giới hạn với partial indexes. Một số index chuyên biệt có giới hạn riêng.

Nếu hệ thống sử dụng sharded collection, cluster key, text/geospatial index hoặc các tính năng nâng cao, hãy kiểm tra tài liệu chính thức của **phiên bản MongoDB và topology cụ thể** trước khi tạo index. Không suy ra mọi option từ index B-tree thông thường đều tương thích với mọi loại index.

### 14.3. Partial index chỉ hỗ trợ các filter operators đã quy định

Không dùng trực giác MQL để nghĩ rằng mọi biểu thức `find()` đều hợp lệ bên trong `partialFilterExpression`.

Ví dụ nếu muốn index những document **thiếu** một field với `$exists: false`, đây không phải một option partial index được hỗ trợ chung như `$exists: true`. Phải thiết kế lại predicate hoặc materialize một flag có ý nghĩa nghiệp vụ như `hasEmail: false` nếu thật sự cần index nhóm đó.

### 14.4. Không dùng unique partial để thay constraint xuyên toàn tập

Một partial unique index trên username khi status ACTIVE **cho phép** các username trùng giữa các document không ACTIVE. Nếu đó là điều nhóm nghiệp vụ không muốn, định nghĩa index đã sai, dù mọi lệnh MongoDB đều chạy đúng.

### 14.5. Index predicate có thể thay đổi theo collation

Khi partial filter có điều kiện so sánh string, collation được sử dụng có thể ảnh hưởng cách xác định phạm vi và cách query kết hợp index. Nếu dùng index có collation chuyên biệt, thiết kế query với collation tương ứng khi cần và kiểm tra explain.

---

## 15. Thực hành: dựng sparse và partial index trong lab

Phần này dùng database `special_index_lab`. Chỉ chạy trên môi trường thử nghiệm.

### 15.1. Tạo dữ liệu

~~~javascript
use special_index_lab

db.users.insertMany([
  {
    _id: "U-001",
    name: "An",
    status: "ACTIVE",
    email: "an@example.test",
    score: 92
  },
  {
    _id: "U-002",
    name: "Bình",
    status: "ACTIVE",
    score: 85
  },
  {
    _id: "U-003",
    name: "Chi",
    status: "INACTIVE",
    email: null,
    score: 73
  },
  {
    _id: "U-004",
    name: "Dung",
    status: "ACTIVE",
    email: "dung@example.test",
    score: 95
  },
  {
    _id: "U-005",
    name: "Hà",
    status: "INACTIVE",
    score: 81
  },
  {
    _id: "U-006",
    name: "Lan",
    status: "ACTIVE",
    email: null,
    score: 88
  },
  {
    _id: "U-007",
    name: "Mai",
    status: "DELETED",
    email: "mai@example.test",
    score: 90
  }
]);
~~~

Quan sát:

~~~javascript
db.users.find().sort({ _id: 1 });
~~~

Các case:

| Document | Status | Email |
|---|---|---|
| U-001 | ACTIVE | string |
| U-002 | ACTIVE | Missing |
| U-003 | INACTIVE | null |
| U-004 | ACTIVE | string |
| U-005 | INACTIVE | Missing |
| U-006 | ACTIVE | null |
| U-007 | DELETED | string |

### 15.2. Tạo sparse index

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    sparse: true,
    name: "idx_email_sparse"
  }
);
~~~

Index có entry cho U-001, U-003, U-004, U-006 và U-007. Bỏ qua U-002/U-005 vì không có field email.

Thử query:

~~~javascript
db.users.find({
  email: "an@example.test"
});

db.users.find({
  email: { $exists: true }
});

db.users.find({
  email: null
});
~~~

Với query cuối, cần nhớ rằng document thiếu email cũng thỏa điều kiện equality null, nên sparse index không chứa đủ mọi kết quả.

### 15.3. Tạo partial index theo trạng thái

~~~javascript
db.users.createIndex(
  { score: -1, _id: 1 },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_score"
  }
);
~~~

Truy vấn danh sách ACTIVE:

~~~javascript
db.users.find({
  status: "ACTIVE"
}).sort({
  score: -1,
  _id: 1
});
~~~

Document U-001, U-002, U-004 và U-006 thuộc phạm vi index này; U-003, U-005 và U-007 không thuộc.

Truy vấn score của mọi status:

~~~javascript
db.users.find({}).sort({
  score: -1,
  _id: 1
});
~~~

không nên được giải quyết chỉ bằng partial index ACTIVE, vì như vậy sẽ thiếu document ngoài ACTIVE.

### 15.4. Quan sát kế hoạch truy vấn

~~~javascript
db.users
  .find({ status: "ACTIVE" })
  .sort({ score: -1, _id: 1 })
  .explain("executionStats");

db.users
  .find({})
  .sort({ score: -1, _id: 1 })
  .explain("executionStats");
~~~

Ghi lại index được dùng, `nReturned`, `totalKeysExamined` và `totalDocsExamined`. Với chỉ bảy document, planner có thể chọn scan vì dữ liệu quá nhỏ; không lấy thời gian đo từ lab này làm benchmark production.

### 15.5. Thử unique partial với email string

Vì U-003 và U-006 có email null, tạo **unique sparse** ngay trên chính field email sẽ gặp rủi ro duplicate key. Dùng partial filter string:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "uk_email_string"
  }
);
~~~

Nếu MongoDB phiên bản/tập index hiện có áp dụng các giới hạn về cùng key pattern, hãy dùng collection lab khác hoặc dọn index cũ theo cách có chủ đích trước khi tạo. Mục tiêu là quan sát uniqueness trong phạm vi string, không phải ép hai định nghĩa index xung đột cùng tồn tại.

Thử insert trùng email:

~~~javascript
db.users.insertOne({
  _id: "U-008",
  name: "Ngọc",
  status: "ACTIVE",
  email: "an@example.test",
  score: 80
});
~~~

Có thể gặp duplicate key error vì `"an@example.test"` đã có và thuộc filter.

Thử tạo user không email:

~~~javascript
db.users.insertOne({
  _id: "U-009",
  name: "Quân",
  status: "ACTIVE",
  score: 77
});
~~~

Việc thiếu email không vi phạm unique partial index này.

### 15.6. Xem metadata

~~~javascript
db.users.getIndexes();
db.users.stats();

db.users.aggregate([
  { $indexStats: {} }
]);
~~~

Kiểm tra `sparse` và `partialFilterExpression` trong metadata, thay vì chỉ dựa vào tên index.

---

## 16. Ví dụ nghiệp vụ 1: chỉ index đơn hàng đang mở

### 16.1. Bài toán

Collection `orders` giữ 5 triệu đơn trong nhiều năm, nhưng chỉ khoảng 100 nghìn đơn ở trạng thái OPEN. Dashboard vận hành liên tục tìm các đơn OPEN của từng khách và sắp xếp mới nhất:

~~~javascript
db.orders.find({
  customerId: "C-101",
  status: "OPEN"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 16.2. Index thông thường

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_orders_customer_status_recent"
  }
);
~~~

Index này bao phủ nhiều trạng thái khác nhau; có thể hữu ích nếu các endpoint cũng truy vấn PAID/CANCELED/CLOSED theo khách.

### 16.3. Partial index dành cho OPEN

~~~javascript
db.orders.createIndex(
  {
    customerId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_customer_recent"
  }
);
~~~

Tại sao có thể tốt?

- Chỉ lưu 100 nghìn đơn OPEN, thay vì toàn bộ 5 triệu.
- Query luôn có điều kiện `status: "OPEN"`, nên có thể dùng index an toàn.
- Index key không cần mang `status` vì phạm vi đã cố định ở mức predicate.

Đánh đổi:

- Khi order đổi OPEN → PAID, index entry phải bị xóa.
- Endpoint xem lịch sử PAID không thể chỉ dùng index này.
- Nếu số lượng OPEN tăng mạnh, lợi ích về kích thước giảm.
- Nếu ứng dụng quên điều kiện status trong query, planner có thể không chọn index.

Không thể nói partial luôn nhanh hơn index thông thường nếu chưa đo số key, kích thước, cache và read/write latency.

---

## 17. Ví dụ nghiệp vụ 2: email tùy chọn nhưng unique

### 17.1. Hai kiểu dữ liệu khác nhau dẫn tới index khác nhau

**Thiết kế A:** Không có email thì **bỏ hẳn field**.

~~~javascript
{ _id: "A", name: "An" }
{ _id: "B", name: "Bình" }
{ _id: "C", name: "Chi", email: "chi@example.test" }
~~~

Unique sparse có thể phù hợp:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    sparse: true,
    name: "uk_email_sparse"
  }
);
~~~

**Thiết kế B:** Không có email có thể lưu `null`.

~~~javascript
{ _id: "A", name: "An", email: null }
{ _id: "B", name: "Bình", email: null }
{ _id: "C", name: "Chi", email: "chi@example.test" }
~~~

Unique sparse không cho phép nhiều indexed null theo quy tắc unique đơn trường thông thường. Partial unique theo kiểu string có thể phù hợp hơn:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "uk_email_string"
  }
);
~~~

### 17.2. Thêm validation

Nếu email khi có phải là string:

~~~javascript
db.createCollection("validated_accounts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        email: {
          bsonType: ["string", "null"]
        }
      }
    }
  }
});
~~~

Ví dụ validator trên cho phép null hoặc string, nhưng chưa kiểm tra cú pháp email hợp lệ. Application còn cần validation về chuỗi rỗng, khoảng trắng và quy tắc email cụ thể.

Unique partial index bảo đảm uniqueness **trong tập hợp các email string**. Nó không bảo đảm email đúng định dạng hoặc field không bao giờ có number nếu thiếu validator.

---

## 18. Ví dụ nghiệp vụ 3: index dữ liệu còn hiệu lực

Một collection `coupons` chứa nhiều voucher đã hết hạn, nhưng API thường truy vấn voucher có trạng thái ACTIVE và chưa hết thời hạn.

Nếu tạo partial index với điều kiện động theo **thời điểm hiện tại**, cần thận trọng. `partialFilterExpression` không phải một bộ lọc tự chuyển động mỗi giây theo clock của ứng dụng. Không nên giả định có thể dùng một giá trị "now" động trong định nghĩa index và server sẽ tự cập nhật phạm vi chỉ vì thời gian trôi.

Thiết kế thông dụng hơn:

~~~javascript
db.coupons.createIndex(
  {
    customerId: 1,
    expiresAt: 1
  },
  {
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "idx_active_coupons_expiry"
  }
);
~~~

Query:

~~~javascript
db.coupons.find({
  customerId: "C-101",
  status: "ACTIVE",
  expiresAt: { $gt: new Date() }
}).sort({
  expiresAt: 1
});
~~~

Ý nghĩa:

- Partial index lọc **trạng thái ACTIVE**.
- Range predicate trên `expiresAt` nằm trong query tại thời điểm thực thi.
- Ứng dụng hoặc tác vụ nền cần quản lý trạng thái ACTIVE của voucher theo nghiệp vụ.
- Một voucher đã quá hạn nhưng vẫn status ACTIVE có thể còn index entry; query range loại nó khi đọc.

Cách này tách predicate ổn định của index khỏi điều kiện thời gian luôn thay đổi trong query.

---

## 19. Quản lý vòng đời index trong production

### 19.1. Không thể sửa tùy ý filter của index có sẵn

Nếu index hiện tại:

~~~javascript
{
  key: { createdAt: -1 },
  partialFilterExpression: {
    status: "OPEN"
  }
}
~~~

và muốn mở rộng thành OPEN hoặc PENDING, không nên giả định có thể gọi lại `createIndex` cùng tên để cập nhật predicate tại chỗ. Index definition cần được quản lý qua quy trình tạo index mới hoặc thay thế theo khả năng hỗ trợ của phiên bản.

Một kế hoạch migration có thể gồm:

1. Chốt workload và filter mới.
2. Kiểm tra dữ liệu đang tồn tại, uniqueness nếu có.
3. Tạo index mới với tên khác khi cấu hình cho phép.
4. Chạy query explain và benchmark trên dữ liệu đại diện.
5. Chuyển ứng dụng dùng query mới.
6. Xác minh không còn phụ thuộc index cũ.
7. Chỉ sau đó drop index cũ theo quy trình change management.

Nếu thay unique index, cần chú ý khoảng thời gian có/không có ràng buộc, dữ liệu ghi đồng thời và nguy cơ trùng key.

### 19.2. Index build trên collection lớn

Trước khi tạo:

~~~javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    partialFilterExpression: {
      status: "OPEN"
    },
    name: "idx_open_customer"
  }
);
~~~

cần cân nhắc:

- CPU, disk I/O, cache và storage headroom.
- Dung lượng index sau build.
- Số lượng document phải đọc trong quá trình build.
- Khả năng unique index build thất bại do dữ liệu trùng.
- Tải production, window triển khai và giám sát.
- Replica set và sharded deployment nếu có.

Partial index chỉ chứa một phần document sau khi build nhưng quá trình tạo index vẫn cần xác định document nào thỏa filter, nên không đồng nghĩa build luôn rẻ.

### 19.3. Khi drop index

~~~javascript
db.orders.dropIndex(
  "idx_open_customer"
);
~~~

Lệnh này thay đổi khả năng truy vấn/đảm bảo uniqueness của hệ thống nếu index được dùng cho ràng buộc. Chỉ thực hiện sau khi có bằng chứng index cũ không còn cần thiết hoặc có index thay thế đáp ứng yêu cầu.

Không drop index production chỉ vì `$indexStats` ghi 0 lượt truy cập trong một cửa sổ ngắn. Một unique index ít được scan vẫn có thể là ràng buộc quan trọng chống trùng dữ liệu.

### 19.4. Đặt tên index thể hiện ý định

Tên rõ ràng giúp vận hành:

~~~text
idx_users_phone_sparse
uk_accounts_email_string
idx_open_orders_customer_recent
idx_active_tickets_priority
idx_coupons_active_expiry
~~~

Không chỉ gọi tên `index_1` hoặc `idx_test` trong production nếu hệ thống có nhiều index và migration. Index name là một phần của kế hoạch vận hành, logs, explain và change management.

---

## 20. Những lỗi và hiểu lầm thường gặp

### "Sparse index bỏ qua null"

**Sai.** Sparse index đơn trường bỏ qua document **thiếu field**, còn document có field với `null` vẫn được index.

### "Unique sparse cho phép vô hạn giá trị null"

**Sai** với unique sparse index đơn trường thông thường. Nhiều document thiếu field được phép, nhưng những document có field `null` có thể xung đột khóa null.

### "Partial index chỉ có thể lọc trên field indexed"

**Sai.** Partial index có thể xây key trên `createdAt` nhưng filter theo `status`.

### "Query nào có sort giống index cũng sử dụng được partial index"

**Sai.** Index phải bao gồm đủ các document query cần. Nếu query cần CLOSED nhưng partial chỉ có OPEN, sử dụng index như nguồn duy nhất sẽ không đầy đủ.

### "Force hint là cách làm index được chọn tốt hơn"

**Rủi ro.** Hint lên sparse/partial index không chứa đủ kết quả có thể khiến query trả thiếu document. Phải chứng minh tính đúng đắn trước.

### "Partial unique bảo đảm uniqueness toàn collection"

**Sai.** Nó chỉ ràng buộc các document thỏa filter.

### "Một index nhỏ thì luôn nhanh hơn"

Không nhất thiết. Planner có thể không dùng index, các thao tác ra/vào tập con làm tăng công ghi, và việc đọc còn phụ thuộc cache, index key, selectivity và lượng data returned.

### "Chỉ cần index là không cần validator"

**Sai.** Index kiểm soát entry/ràng buộc khóa; validator kiểm soát cấu trúc/kiểu document. Một partial filter có thể chỉ bỏ qua document sai kiểu, không ngăn lưu chúng.

### "Compound sparse chỉ index document có tất cả field"

Không đúng với compound sparse gồm ascending/descending keys thông thường: một document có ít nhất một field indexed có thể góp entry. Cần đọc quy tắc theo loại compound index.

### "Có thể đặt sparse: true và partialFilterExpression cùng nhau"

**Không.** Hai options không kết hợp trong cùng một định nghĩa index.

### "Đổi partial filter bằng cách tạo lại index trùng tên là được"

Không nên giả định. Index definition phải được quản lý qua quy trình migration/index replacement phù hợp.

### "Dữ liệu hết hạn theo thời gian tự biến mất khỏi partial index"

Không vì clock ứng dụng trôi. Predicate của index không phải đồng hồ động. Nếu dùng trạng thái ACTIVE, document phải được update status hoặc xóa theo chính sách nghiệp vụ; query vẫn có thể lọc thêm `expiresAt` tại thời điểm đọc.

---

## 21. Bài tập thực hành

### Bài tập 1 — Sparse và null

Trong `special_index_lab`, tạo sáu document với:

1. Hai document có `phone` là string khác nhau.
2. Hai document **thiếu** `phone`.
3. Hai document có `phone: null`.

Tạo `{phone:1}` sparse không unique. Trình bày document nào được index. Sau đó thử unique sparse index trên collection khác có cùng dữ liệu; giải thích vì sao index có thể thất bại với hai null.

### Bài tập 2 — Partial unique cho email string

Thiết kế một collection account cho phép:

- Nhiều user không có field email.
- Nhiều user có email null.
- Email dạng string không được trùng.
- Không cho email dạng number trong dữ liệu mới.

Hãy chọn partial unique index và thêm validator thích hợp. Giải thích tại sao một mình index chưa bảo đảm kiểu dữ liệu hợp lệ.

### Bài tập 3 — Chọn index cho dashboard

Collection orders có 5 triệu document, chỉ 2% còn OPEN. Dashboard truy vấn:

~~~javascript
db.orders.find({
  customerId: "C-101",
  status: "OPEN"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Đề xuất compound partial index, giải thích key và filter. Nêu hai query mà index này **không** bao phủ đủ dữ liệu.

### Bài tập 4 — Query planner eligibility

Partial index:

~~~javascript
db.tickets.createIndex(
  { updatedAt: -1 },
  {
    partialFilterExpression: {
      priority: { $gte: 4 }
    }
  }
);
~~~

Với mỗi query dưới, cho biết tập kết quả có nằm trong tập được index không:

~~~javascript
// A
db.tickets.find({
  priority: { $gte: 5 }
});

// B
db.tickets.find({
  priority: { $gte: 2 }
});

// C
db.tickets.find({
  priority: 4
});

// D
db.tickets.find({});
~~~

Giải thích vì sao eligibility không đồng nghĩa planner chắc chắn chọn index.

### Bài tập 5 — Trạng thái và unique partial

Tạo unique partial index trên `username` khi `status: "ACTIVE"`. Insert hai document INACTIVE cùng username, một ACTIVE cùng username. Sau đó thử chuyển một INACTIVE sang ACTIVE. Dự đoán lỗi và giải thích index entry được tạo khi trạng thái thay đổi.

### Bài tập 6 — Đo và so sánh index

Sinh dữ liệu lab với phân bố:

- 80% document thiếu field `phone`.
- 10% có phone null.
- 10% có phone string.

So sánh kích thước index thường, sparse và partial `$type:"string"` trên những collection riêng để không bị giới hạn tạo index trùng key pattern. Chạy explain cho query phone string và query `phone: null`. Phân tích tính đúng đắn, index sizes, key/doc examined và chi phí ghi.

### Bài tập 7 — Compound sparse

Có các document chỉ có email, chỉ có phone, cả hai và thiếu cả hai. Tạo sparse compound index `{email:1,phone:1}`. Giải thích entry nào được tạo. Sau đó thiết kế partial index chỉ nhận document **có cả email và phone là string**.

### Bài tập 8 — Migration index production

Một collection có index thường `{customerId:1,createdAt:-1}`. Nhóm muốn thay bằng partial index chỉ cho status OPEN:

1. Thu thập tất cả query shapes đang dùng index cũ.
2. Xác định endpoint nào vẫn cần đơn CLOSED/PAID.
3. Tạo index mới và kiểm tra explain.
4. Đánh giá dung lượng và write maintenance.
5. Chốt khi nào có thể bỏ index cũ.
6. Thiết kế rollback nếu một endpoint lịch sử bị chậm sau thay đổi.

---

## 22. Câu hỏi ôn tập

1. Sparse index đơn trường loại document nào khỏi index?
2. Vì sao `null` không đồng nghĩa missing?
3. Unique sparse index có thể cho nhiều document thiếu email không?
4. Vì sao hai document có `email: null` có thể xung đột với unique sparse?
5. Partial index khác sparse ở khả năng biểu diễn điều kiện nào?
6. `partialFilterExpression` có thể dùng field khác index key không?
7. Vì sao query chỉ lọc `customerId` có thể không dùng partial index `status: "OPEN"`?
8. Điều kiện gì làm query trở thành tập con của partial filter?
9. `hint()` có thể gây thiếu kết quả như thế nào?
10. Unique partial index có ngăn trùng key ngoài filter không?
11. Vì sao chuyển status INACTIVE → ACTIVE có thể phát sinh duplicate key?
12. Compound sparse gồm ascending keys có quy tắc tạo entry ra sao?
13. Vì sao không nên mặc định `$exists: false` được hỗ trợ trong partial filter?
14. `$type: "string"` loại được null nhưng có loại chuỗi rỗng không?
15. Partial index có tự cập nhật theo đồng hồ cho điều kiện "chưa hết hạn" không?
16. Những metric nào chứng minh index hữu ích cho một query?
17. Vì sao index nhỏ có thể không cải thiện performance?
18. Khi đổi index definition trên production, cần điều tra workload nào trước?
19. Tại sao unique index ít được query vẫn có thể cần giữ?
20. Vì sao index không thay thế schema validation?

## 23. Tổng kết

Sparse index và partial index đều giúp tránh lưu index entry cho những document không phục vụ một nhóm truy vấn, nhưng chúng có ý nghĩa khác nhau:

- **Sparse index:** phù hợp với field tùy chọn, chủ yếu bỏ document **không có field indexed**. Với index đơn trường, field có giá trị `null` **vẫn được index**.
- **Partial index:** giới hạn tập document bằng `partialFilterExpression`, có thể lọc theo status, kiểu BSON, range hoặc điều kiện trên một field khác.
- **Unique sparse/partial:** chỉ bảo đảm uniqueness trong phạm vi document có entry. Khi xử lý email tùy chọn, khác biệt giữa missing và null là cực kỳ quan trọng.
- **Query planner:** phải đảm bảo index không làm query thiếu kết quả. Với sparse/partial index, filter của query phải phù hợp với phạm vi index; đừng ép `hint` chỉ để thấy index được dùng.
- **Vận hành:** đo plan, index size, write cost và tính nhất quán dữ liệu; khi migration index, phải xét cả query lịch sử và unique constraints.

Quy trình thực hành nên là: **xác định nhóm document cần truy vấn → diễn đạt điều kiện thật chính xác → tạo index → xem `getIndexes()` và `explain()` → đo trên dữ liệu đại diện → kiểm tra tác động ghi và kế hoạch thay đổi trong production**.

## Tài liệu MongoDB chính thức tham khảo

- [MongoDB Manual — Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Create Index](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/)
- [MongoDB Manual — $indexStats Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
