# Chỉ mục trên dữ liệu thưa, NULL hoặc trường không tồn tại

## 1. Bài toán: một trường tùy chọn làm truy vấn trở nên khó đoán

Một nền tảng quản lý khách hàng lưu nhiều loại hồ sơ trong cùng collection. Một phần khách đã cung cấp email, một phần chưa; có bản ghi cũ từng lưu email bằng giá trị NULL, trong khi bản ghi mới bỏ hẳn trường khi chưa có thông tin.

~~~json
{"customerId":"C01","name":"An","email":"an@example.com"}
{"customerId":"C02","name":"Bình"}
{"customerId":"C03","name":"Chi","email":null}
{"customerId":"C04","name":"Dũng","email":""}
{"customerId":"C05","name":"Hà","email":"ha@example.com"}
~~~

Ứng dụng cần trả lời những câu hỏi khác nhau:

1. Những khách hàng **đã có email hợp lệ** là ai?
2. Những khách hàng **chưa có thuộc tính email** là ai?
3. Những khách hàng có trường email nhưng **giá trị bằng NULL** là ai?
4. Có thể bắt buộc email **duy nhất khi đã được cung cấp** không?
5. Có thể tạo chỉ mục chỉ chứa một nhóm nhỏ khách hàng để giảm chi phí lưu trữ và truy vấn không?

Nếu coi **missing**, **NULL** và **chuỗi rỗng** là một trạng thái duy nhất, các truy vấn và unique constraint rất dễ cho kết quả ngoài mong đợi. Nếu tạo sparse index nhưng tưởng rằng nó loại cả giá trị NULL, việc đăng ký người dùng có thể thất bại do vi phạm khóa duy nhất. Nếu lọc những bản ghi không có trường bằng một index chỉ chứa các bản ghi có trường, hệ có thể bỏ sót dữ liệu hoặc phải quét rộng.

**Mục tiêu bài học:** hiểu ngữ nghĩa của dữ liệu thưa, NULL và trường không tồn tại; biết index nào thực sự chứa bản ghi nào; viết truy vấn đúng; chọn sparse, partial hay index/bản chiếu riêng; và kiểm chứng hiệu quả mà không đánh đổi tính đúng đắn.

## 2. Ba khái niệm nền tảng

### 2.1. Dữ liệu thưa là gì?

Một tập dữ liệu được gọi là **thưa** theo một thuộc tính khi chỉ có một tỷ lệ nhỏ bản ghi có giá trị cho thuộc tính đó.

Ví dụ 10 triệu sản phẩm nhưng chỉ 200.000 sản phẩm có trường **discountCode**:

~~~text
Tổng sản phẩm                  10.000.000
Sản phẩm có discountCode          200.000
Sản phẩm không có discountCode  9.800.000

Tỷ lệ hiện diện = 200.000 / 10.000.000 = 2%
~~~

Nếu truy vấn chỉ tìm sản phẩm **có discountCode**, một index chỉ bao phủ tập 2% này có thể giảm số entry và chi phí duy trì so với index bao phủ toàn bộ collection. Nhưng nếu truy vấn chủ yếu cần tìm **sản phẩm không có discountCode**, index chỉ chứa 2% bản ghi **không** cung cấp đường truy cập trực tiếp cho 98% còn lại.

**Thưa không có nghĩa giá trị hiếm**: một field có thể xuất hiện trong 100% bản ghi nhưng chỉ có 1% bản ghi mang trạng thái OPEN; một **partial index theo trạng thái OPEN** vẫn có thể rất hữu ích dù field status không thưa.

### 2.2. Missing, NULL và giá trị thực

Cần phân biệt các trạng thái:

| Trạng thái | JSON minh họa | Ý nghĩa có thể có |
| --- | --- | --- |
| **Missing / absent** | Không có khóa email | Chưa cung cấp, không áp dụng hoặc dữ liệu legacy |
| **Explicit NULL** | "email": null | Đã biết thuộc tính nhưng hiện không có giá trị, tùy contract |
| **Empty string** | "email": "" | Chuỗi có độ dài 0, không phải NULL |
| **False** | "verified": false | Giá trị boolean hợp lệ |
| **Zero** | "score": 0 | Giá trị số hợp lệ |
| **Empty array** | "tags": [] | Một collection có 0 phần tử |
| **Non-empty value** | "email": "an@example.com" | Có giá trị |

Hai trạng thái **missing** và **NULL** có thể được nghiệp vụ xem là tương đương, nhưng hệ lưu trữ/index không nhất thiết xem chúng giống nhau. Các giá trị **false**, **0** và chuỗi rỗng cũng không nên bị coi là missing chỉ vì trong một số ngôn ngữ chúng là *falsy*.

### 2.3. NULL không có nghĩa thống nhất trên mọi NoSQL

Trong SQL truyền thống, schema khai báo cột tồn tại, còn giá trị cột có thể là NULL. Trong document database, **trường có thể hoàn toàn không có mặt** trong document. Trong DynamoDB, một item có thể thiếu attribute hoặc chứa attribute kiểu NULL tường minh. Trong Cassandra, gán NULL cho một cột thường biểu thị **xóa giá trị** và tạo tombstone, chứ không lưu một value NULL theo cách MongoDB giữ BSON Null. Trong Elasticsearch, cần xét **giá trị có được lập chỉ mục hay không**, không chỉ xét trường có trong JSON nguồn.

Do đó, câu hỏi đúng luôn là:

> Với engine, kiểu index và phiên bản đang dùng, trạng thái này có tạo entry trong index không, và truy vấn nào có thể tìm được entry đó?

## 3. Dữ liệu thưa tác động thế nào tới index?

Một index có thể hình dung như tập các entry:

~~~text
indexKey -> documentId
~~~

Ví dụ index trên email:

~~~text
"an@example.com" -> C01
"ha@example.com" -> C05
~~~

Nhưng chuyện gì xảy ra với C02, C03 và C04?

- C02 không có email.
- C03 có email: null.
- C04 có email: "".

Kết quả phụ thuộc loại index:

1. **Index thông thường:** có thể giữ entry đại diện cho missing/NULL, tùy hệ.
2. **Sparse index:** bỏ qua một số bản ghi không đủ điều kiện hiện diện của field/key.
3. **Partial/filtered index:** chỉ giữ những bản ghi thỏa biểu thức điều kiện.
4. **Index trên read model riêng:** ứng dụng chủ động tạo bản ghi dẫn xuất cho nhóm trạng thái cần tìm.

Một index thưa có thể nhỏ hơn và rẻ hơn để cập nhật, nhưng **không chứa thông tin về tất cả bản ghi**. Đây vừa là lợi ích vừa là giới hạn quan trọng của nó.

### 3.1. Những câu hỏi index nên phục vụ

| Access pattern | Đường truy cập có thể cân nhắc |
| --- | --- |
| Tìm chính xác khách theo email đã xác thực | Index trên email đã chuẩn hóa, unique theo phạm vi |
| Tìm khách có email không NULL | Index trên giá trị thật / partial theo kiểu dữ liệu |
| Tìm khách chưa từng cung cấp email | Trạng thái rõ ràng hoặc bản chiếu theo trạng thái thiếu |
| Tìm khách có email tường minh bằng NULL | Truy vấn đặc thù hoặc trường trạng thái riêng |
| Lấy 50 đơn OPEN mới nhất | Partial index chỉ cho trạng thái OPEN |
| Liệt kê mọi khách, kể cả missing | Đường đọc/index bao phủ đầy đủ dữ liệu |

Không có một index tối ưu cho toàn bộ sáu truy vấn. Hãy chọn theo **tần suất đọc, độ chọn lọc, tần suất ghi, chi phí lưu trữ và ràng buộc đúng đắn**.

## 4. MongoDB: missing và explicit NULL trong truy vấn

MongoDB phân biệt việc **field không có trong BSON document** với field có **BSON Null**. Nhưng một số cú pháp query cố ý khớp cả hai.

Chuẩn bị dữ liệu mẫu trong một collection riêng:

~~~javascript
db.customers.insertMany([
  { _id: "C01", name: "An",   email: "an@example.com" },
  { _id: "C02", name: "Binh" },
  { _id: "C03", name: "Chi",  email: null },
  { _id: "C04", name: "Dung", email: "" },
  { _id: "C05", name: "Ha",   email: "ha@example.com" }
]);
~~~

### 4.1. Truy vấn email bằng NULL

~~~javascript
db.customers.find({ email: null });
~~~

Với cấu trúc mẫu, truy vấn này khớp **C02 và C03**:

- C02 **không có** trường email.
- C03 **có** trường email nhưng value là null.

**Điểm dễ nhầm:** điều kiện **{ email: null }** trong MongoDB không đồng nghĩa “chỉ document chứa field với BSON Null”.

### 4.2. Chỉ tìm trường không tồn tại

~~~javascript
db.customers.find({
  email: { $exists: false }
});
~~~

Với dữ liệu mẫu, truy vấn trả **C02**. Nó hỏi về **sự hiện diện của field**, không phải nội dung field.

### 4.3. Chỉ tìm trường có mặt

~~~javascript
db.customers.find({
  email: { $exists: true }
});
~~~

Với mẫu, kết quả là **C01, C03, C04 và C05**. Trường email của C03 tồn tại dù giá trị bằng null; email của C04 tồn tại dù là chuỗi rỗng.

### 4.4. Tìm explicit BSON Null

~~~javascript
db.customers.find({
  email: { $type: "null" }
});
~~~

Hoặc dùng mã BSON type 10:

~~~javascript
db.customers.find({
  email: { $type: 10 }
});
~~~

Với các document mẫu có email scalar, kết quả là **C03**. Khi field có thể chứa array hoặc nested data, phải lưu ý semantics của toán tử **$type** đối với phần tử trong array; đừng tự mở rộng kết luận “scalar null duy nhất” sang mọi hình dạng dữ liệu mà không có test.

### 4.5. Non-null không đồng nghĩa email hợp lệ

~~~javascript
db.customers.find({
  email: { $ne: null }
});
~~~

Điều kiện này tìm các trường có giá trị khác null theo semantics MongoDB, nhưng có thể bao gồm **email = ""**, dữ liệu sai kiểu hoặc chuỗi không đúng định dạng email. **Có giá trị không NULL** là điều kiện kỹ thuật, **email hợp lệ** là điều kiện nghiệp vụ.

Nếu ứng dụng chỉ cho email là string đã chuẩn hóa, validator và domain validation nên đảm bảo dữ liệu thuộc miền hợp lệ trước khi index.

### 4.6. Bảng kết quả trên tập mẫu

| Truy vấn MongoDB | C01 | C02 (missing) | C03 (null) | C04 ("") | C05 |
| --- | --- | --- | --- | --- | --- |
| { email: null } | Không | Có | Có | Không | Không |
| { email: { $exists: false } } | Không | Có | Không | Không | Không |
| { email: { $exists: true } } | Có | Không | Có | Có | Có |
| { email: { $type: "null" } } | Không | Không | Có | Không | Không |
| { email: "an@example.com" } | Có | Không | Không | Không | Không |

Bảng sử dụng **email scalar** trong bộ dữ liệu mẫu. Các toán tử với nested field, array, regex, collation hoặc BSON type hỗn hợp có thể có thêm trường hợp cần kiểm tra.

## 5. MongoDB sparse index thực sự chứa những gì?

Tạo sparse index đơn trường:

~~~javascript
db.customers.createIndex(
  { email: 1 },
  { sparse: true, name: "email_sparse_idx" }
);
~~~

Với MongoDB, một sparse index trên field thường **chỉ chứa document có field đó**, kể cả khi giá trị của field là **null**; nó bỏ qua document hoàn toàn thiếu field.

Vì vậy với mẫu ở trên:

| Document | email | Có entry trong sparse index email? |
| --- | --- | --- |
| C01 | "an@example.com" | Có |
| C02 | Missing | **Không** |
| C03 | null | **Có** |
| C04 | "" | **Có** |
| C05 | "ha@example.com" | Có |

Đây là sự khác biệt cần nhớ:

> **Sparse không phải là “NOT NULL index” trong MongoDB.**

Index thông thường một trường trong MongoDB có thể tạo entry đại diện cho document thiếu field, còn sparse index bỏ qua những document đó. Tuy nhiên, **entry đại diện cho missing và explicit null không tự cung cấp khả năng phân biệt hai trạng thái chỉ bằng khóa index**; planner có thể cần đọc document gốc để xác định field có thật hay không.

### 5.1. Vì sao sparse index có thể trả kết quả thiếu?

Xét yêu cầu:

~~~javascript
db.customers.find().sort({ email: 1 });
~~~

Yêu cầu là lấy **mọi customer**, kể cả C02 không có email. Nếu chỉ duyệt sparse index email, C02 bị bỏ sót. Vì vậy query planner MongoDB thường **không chọn sparse index khi nó sẽ làm tập kết quả không đầy đủ**.

Nếu người lập trình cố ép index bằng **hint()**, họ có thể nhận **kết quả thiếu**:

~~~javascript
db.customers
  .find({})
  .sort({ email: 1 })
  .hint("email_sparse_idx");
~~~

Không dùng hint để “cải thiện hiệu năng” trước khi chứng minh index bao phủ đầy đủ kết quả cần tìm. Với sparse/partial index, **độ đầy đủ của tập dữ liệu quan trọng hơn tốc độ thực thi**.

### 5.2. Truy vấn phù hợp hơn với sparse index

Ví dụ tìm các customer có field email:

~~~javascript
db.customers.find({
  email: { $exists: true }
});
~~~

Điều kiện **$exists: true** phù hợp với phạm vi document được đưa vào sparse index. Tùy projection, index và optimizer, truy vấn có thể vẫn cần fetch document; không nên mặc định nó là covered query chỉ vì dùng sparse index.

Ngược lại:

~~~javascript
db.customers.find({
  email: { $exists: false }
});
~~~

không thể được đáp ứng bằng cách đơn giản duyệt sparse index email, vì chính các document cần tìm **không có entry trong đó**.

### 5.3. Compound sparse index cần xét quy tắc riêng

Một chỉ mục ghép:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, email: 1 },
  { sparse: true }
);
~~~

**Không được suy luận** rằng mọi document thiếu email chắc chắn không nằm trong index ghép. Với MongoDB, điều kiện tồn tại của một **compound sparse index** còn phụ thuộc các loại thành phần index, và quy tắc không đơn giản bằng sparse index **đơn trường**. Ví dụ với các key thành phần kiểu ascending/descending thông thường, document có ít nhất một field đã index có thể vẫn được đưa vào index.

Nếu tenantId có mặt trên mọi document, chỉ thêm **sparse: true** vào chỉ mục ghép (tenantId, email) có thể **không giúp lọc bớt document thiếu email** như mong muốn. Khi cần điều kiện chỉ index document có email, hãy cân nhắc **partialFilterExpression** tường minh.

## 6. MongoDB unique sparse index: thiếu trường khác NULL

Giả sử nghiệp vụ yêu cầu:

> Email phải duy nhất khi người dùng cung cấp, nhưng nhiều người có thể chưa nhập email.

Một lựa chọn:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    sparse: true,
    name: "email_unique_sparse"
  }
);
~~~

Với chỉ mục **unique + sparse đơn trường**:

- Có thể có **nhiều document thiếu email**, vì chúng không tạo index entry.
- Không thể có hai document cùng giá trị email đã index.
- **Explicit null cũng được index**, nên trong mô hình đơn trường điển hình chỉ có thể có **một document có email: null**.
- Chuỗi rỗng **""** là một giá trị đã index; nhiều document cùng "" có thể gây duplicate key.

### 6.1. Ví dụ tình huống thêm user

Giả sử index được tạo trên collection sạch:

~~~javascript
db.users.insertOne({ _id: "U01", name: "An" });
db.users.insertOne({ _id: "U02", name: "Binh" });
// Hai user không có email đều có thể được thêm.

db.users.insertOne({ _id: "U03", email: null });
// Một explicit null được index.

db.users.insertOne({ _id: "U04", email: null });
// Có thể bị từ chối do duplicate key.
~~~

Nếu dữ liệu hiện tại đã có nhiều giá trị trùng trong phạm vi index, **tạo unique index** cũng có thể thất bại. Cần thống kê và xử lý dữ liệu legacy trước khi thêm constraint.

### 6.2. Chuẩn hóa email trước khi áp unique constraint

Unique index kỹ thuật không tự giải quyết ngữ nghĩa:

~~~text
An@Example.com
an@example.com
 an@example.com 
~~~

Tùy nghiệp vụ và chuẩn xử lý email, các chuỗi này có thể cần được coi là tương đương ở một số khía cạnh. Không nên đơn giản lowercase mọi ký tự địa chỉ email nếu hợp đồng không cho phép; cần xây quy tắc chuẩn hóa cụ thể, kiểm tra whitespace, Unicode và collation theo chính sách hệ.

Nếu hệ nhiều tenant, có thể cần unique **trong mỗi tenant**, không phải global:

~~~text
(tenantId, normalizedEmail) unique
~~~

Khả năng thực thi unique xuyên shard/partition phải được kiểm tra theo thiết kế database cụ thể.

## 7. MongoDB partial index: lọc theo điều kiện thực sự cần

Khi muốn chỉ index document thỏa một điều kiện cụ thể, **partial index** thường linh hoạt hơn sparse index.

Ví dụ chỉ index email kiểu string:

~~~javascript
db.users.createIndex(
  { email: 1 },
  {
    name: "email_string_only",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

Index này bỏ qua các document không có email hoặc email = null, vì chúng không thỏa **$type: "string"**. Nhưng **email = ""** vẫn là một string; muốn loại chuỗi rỗng cần thêm quy tắc dữ liệu hoặc filter thích hợp được engine hỗ trợ.

### 7.1. Unique partial index theo kiểu dữ liệu

Nếu muốn các email dạng string phải unique:

~~~javascript
db.users.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    name: "unique_tenant_email_string",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

Điểm cần hiểu:

1. Ràng buộc unique chỉ áp dụng cho **document khớp partial filter**.
2. Các document thiếu email/null không tham gia index này.
3. Một document có email kiểu number/object cũng không tham gia; đó **không phải hành vi nên cho phép** nếu ứng dụng quy định email luôn là string.
4. Dùng thêm validator và validation nghiệp vụ để ngăn dữ liệu sai type.
5. Trước khi triển khai trên sharded collection, kiểm tra phạm vi unique constraint, shard key và version MongoDB.

Không nên dùng partial index để thay thế ràng buộc **email phải hợp lệ và thuộc đúng tenant**. Index bảo vệ một dạng uniqueness theo phạm vi đã khai báo, không biết email đã được xác minh sở hữu hay chưa.

### 7.2. Partial index theo trạng thái nghiệp vụ

Giả sử chỉ 3% đơn hàng đang OPEN, còn 97% đã CLOSED. API thường lấy 50 đơn OPEN mới nhất của một tenant.

~~~javascript
db.orders.createIndex(
  { tenantId: 1, updatedAt: -1, orderId: 1 },
  {
    name: "open_orders_by_tenant",
    partialFilterExpression: {
      status: "OPEN"
    }
  }
);
~~~

Truy vấn:

~~~javascript
db.orders
  .find({
    tenantId: "T01",
    status: "OPEN"
  })
  .sort({
    updatedAt: -1,
    orderId: 1
  })
  .limit(50);
~~~

Khi index phù hợp và optimizer lựa chọn nó, chỉ mục chỉ cần chứa các đơn OPEN trong phạm vi filter, thay vì mọi đơn CLOSED lịch sử.

### 7.3. Query phải hàm ý điều kiện của partial index

Partial index **không** tự động phục vụ mọi truy vấn liên quan tới tenantId.

Ví dụ:

~~~javascript
db.orders.find({ tenantId: "T01" });
~~~

Truy vấn trên cần cả OPEN lẫn CLOSED. Nếu dùng partial index OPEN đơn thuần, kết quả sẽ thiếu CLOSED. Vì vậy planner không thể chọn nó như đường đọc đầy đủ.

Tương tự:

~~~javascript
db.orders.find({
  tenantId: "T01",
  status: { $ne: "CLOSED" }
});
~~~

Với dữ liệu có thêm PENDING, CANCELLED hoặc missing status, điều kiện “khác CLOSED” **không tương đương “OPEN”**. Đừng mặc định query kiểu này sẽ sử dụng partial index status = OPEN.

Nguyên tắc quan trọng:

> Query predicate phải **bảo đảm** kết quả nằm trong tập document mà partial index bao phủ; nếu không, dùng index sẽ có nguy cơ thiếu dữ liệu.

### 7.4. Sparse khác partial ở đâu?

| Tính chất | MongoDB sparse index | MongoDB partial index |
| --- | --- | --- |
| Tiêu chí chính | Field/index key hiện diện theo quy tắc sparse | Document khớp filter expression |
| Explicit null của field đơn | Vẫn được index nếu field có mặt | Phụ thuộc filter |
| Loại bản ghi theo status | Không trực tiếp bằng điều kiện tùy ý | Có thể dùng filter status=OPEN |
| Chỉ index email kiểu string | Sparse đơn trường không đủ | Có thể dùng $type:string |
| Query planner | Tránh dùng khi kết quả bị thiếu | Tránh dùng khi query không hàm ý filter |
| Unique constraint | Chỉ áp dụng cho entry hiện diện | Chỉ áp dụng cho document khớp filter |

Partial index thường thể hiện **ý định nghiệp vụ rõ ràng hơn**, nhưng không có nghĩa mọi tổ hợp toán tử đều được hỗ trợ trong partialFilterExpression. Cần dùng tập toán tử mà phiên bản MongoDB hỗ trợ và kiểm tra query plan.

## 8. Truy vấn missing thường khó hơn truy vấn giá trị có mặt

Một index chỉ lưu các giá trị **hiện diện** dễ trả lời:

~~~text
email = "an@example.com"
status = "OPEN"
discountCode = "NEWUSER"
~~~

Nhưng yêu cầu:

~~~text
Lấy mọi document mà email không tồn tại
~~~

chính là tìm các bản ghi **không có entry trong index đó**.

### 8.1. Vì sao quét sparse index không tìm được missing?

Giả sử:

~~~text
Collection:
  C01 email present
  C02 email missing
  C03 email missing
  C04 email present

Sparse index:
  email(C01)
  email(C04)
~~~

Từ riêng sparse index, ta không biết C02 và C03 là những document nào; index chỉ chứa **phần tập có field**. Để tìm tập còn lại, engine có thể phải xem thêm cấu trúc truy cập khác hoặc quét collection.

### 8.2. Đổi bài toán thành trạng thái được lập chỉ mục

Nếu truy vấn “khách chưa điền email” là một màn hình vận hành nóng, cân nhắc lưu **trạng thái tường minh**:

~~~json
{
  "customerId": "C02",
  "emailState": "NOT_PROVIDED"
}
~~~

Với khách có email:

~~~json
{
  "customerId": "C01",
  "email": "an@example.com",
  "emailState": "VERIFIED"
}
~~~

Có thể index emailState:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, emailState: 1, updatedAt: -1 }
);
~~~

Truy vấn:

~~~javascript
db.customers
  .find({
    tenantId: "T01",
    emailState: "NOT_PROVIDED"
  })
  .sort({ updatedAt: -1 })
  .limit(50);
~~~

Đổi lại, hệ phải bảo đảm **emailState luôn tương thích với email** qua tất cả đường ghi và migration. Nếu email được thay đổi nhưng emailState bị quên cập nhật, index đúng về mặt kỹ thuật nhưng sai về nghiệp vụ.

### 8.3. Khi nào trạng thái riêng tốt hơn kiểm tra thiếu field?

Một trường trạng thái riêng thường hữu ích khi:

- Màn hình nghiệp vụ thường xuyên lọc “chưa bổ sung / đã xác minh / bị từ chối”.
- Cần phân biệt “không áp dụng” với “chưa thu thập”.
- Truy vấn trên missing chiếm tỷ lệ lớn hoặc có SLA nghiêm ngặt.
- Nhiều service cùng ghi dữ liệu và đã có quy trình đồng bộ state.
- Cần phân trang theo thời gian hoặc ưu tiên xử lý một nhóm missing.

Nếu chỉ thỉnh thoảng chạy một job kiểm tra chất lượng dữ liệu, full scan có kiểm soát hoặc batch audit có thể hợp lý hơn việc thêm nhiều trường/index duy trì suốt vòng đời ứng dụng.

## 9. DynamoDB: sparse Global Secondary Index bằng cách bỏ attribute khóa

Trong DynamoDB, một **Global Secondary Index (GSI)** có key schema riêng. Nếu item **thiếu** thuộc tính partition key của GSI, hoặc thiếu sort key khi GSI yêu cầu cả hai, item đó **không có entry trong GSI**.

Đây là một cách tạo index thưa **bằng mô hình dữ liệu**, khác với tùy chọn sparse:true của MongoDB.

### 9.1. Ví dụ: chỉ index đơn cần duyệt

Base table:

~~~text
Table: Orders
PK = TENANT#T01
SK = ORDER#O1001
~~~

Đơn cần duyệt:

~~~json
{
  "PK": "TENANT#T01",
  "SK": "ORDER#O1001",
  "orderId": "O1001",
  "reviewState": "NEEDS_REVIEW",
  "GSI1PK": "REVIEW#T01",
  "GSI1SK": "2026-11-14T08:30:00.000Z#O1001"
}
~~~

Đơn đã hoàn thành:

~~~json
{
  "PK": "TENANT#T01",
  "SK": "ORDER#O1002",
  "orderId": "O1002",
  "reviewState": "APPROVED"
}
~~~

Giả sử GSI1 được khai báo với:

~~~text
GSI1 partition key = GSI1PK (String)
GSI1 sort key      = GSI1SK (String)
~~~

Chỉ item O1001 có đầy đủ GSI1PK và GSI1SK hợp lệ, nên nó tham gia chỉ mục này. O1002 không có hai key đó, nên không xuất hiện trong GSI1.

Khi API cần lấy các đơn cần duyệt của T01:

~~~text
Query GSI1 where GSI1PK = REVIEW#T01
order by GSI1SK
~~~

Đường đọc dự kiến chỉ chạm nhóm NEEDS_REVIEW thay vì quét toàn bộ Orders.

### 9.2. Không dùng DynamoDB NULL làm GSI key

DynamoDB phân biệt:

- Attribute **không tồn tại** trong item.
- Attribute có kiểu **NULL** tường minh.
- Attribute có kiểu string, number hoặc binary hợp lệ để dùng làm key.

Thuộc tính khóa index phải đáp ứng yêu cầu key schema/kiểu dữ liệu của DynamoDB; **NULL không phải kiểu khóa index hợp lệ**. Khi muốn item không tham gia GSI, cách phù hợp thường là **bỏ hẳn GSI key attributes**, không phải gán chúng bằng NULL hay chuỗi rỗng.

### 9.3. Chuyển trạng thái phải cập nhật GSI key

Khi O1001 được duyệt:

~~~text
Trước:
  reviewState = NEEDS_REVIEW
  GSI1PK = REVIEW#T01
  GSI1SK = ...

Sau:
  reviewState = APPROVED
  GSI1PK bị REMOVE
  GSI1SK bị REMOVE
~~~

Base item phải cập nhật trạng thái và xóa key dẫn xuất bằng thao tác ghi/điều kiện phù hợp. Khi thay đổi base item được lan truyền sang GSI, entry cũ sẽ bị gỡ khỏi chỉ mục.

**GSI có tính nhất quán sau cùng**: trong một khoảng thời gian ngắn, Query GSI vẫn có thể trả item vừa chuyển trạng thái. Nếu quyết định phê duyệt có hậu quả quan trọng, không được chỉ tin read model/GSI chưa hội tụ; cần kiểm tra nguồn authoritative trước khi cam kết.

### 9.4. attribute_exists và attribute_not_exists

Trong DynamoDB expression:

~~~text
attribute_exists(email)
attribute_not_exists(email)
~~~

được dùng để kiểm tra sự hiện diện của attribute theo semantics DynamoDB. Một attribute có giá trị kiểu **NULL tường minh** vẫn là attribute **có tồn tại**.

Lưu ý:

- Trong Query, key condition vẫn cần những điều kiện hợp lệ trên **partition key** và tùy chọn sort key.
- **FilterExpression** kiểm tra giá trị sau khi DynamoDB đã đọc/đánh giá các item theo đường truy cập; nó không biến truy vấn không khóa thành một index scan tối ưu.
- Không thể dùng attribute_not_exists trên một attribute tùy chọn thay thế việc thiết kế một GSI hoặc bảng phục vụ truy vấn missing nếu đây là access pattern nóng.

### 9.5. Phân biệt sparse GSI và projection attributes

**Index key attributes** quyết định item có tham gia GSI hay không. **Projection** quyết định các thuộc tính bổ sung nào được sao chép vào GSI. Việc một attribute thông thường không được project **không đồng nghĩa item bị loại khỏi GSI**.

Ví dụ GSI1 chỉ project orderId và reviewState có thể vẫn chứa item có GSI1PK/GSI1SK hợp lệ; thiếu một field khác chỉ ảnh hưởng dữ liệu trả về từ index, không tự làm index trở nên sparse theo field đó.

## 10. Cassandra: NULL thường biểu thị xóa giá trị

Cassandra là wide-column database nhưng **ngữ nghĩa NULL khác document MongoDB**. Với các cột không thuộc primary key, đặt giá trị NULL trong CQL write thường được hiểu như **xóa cột/cell tương ứng**, có thể tạo tombstone. Việc không cập nhật cột và việc gán NULL tường minh không giống nhau.

Giả sử table:

~~~sql
CREATE TABLE profiles_by_id (
    tenant_id text,
    profile_id text,
    display_name text,
    nickname text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id), profile_id)
);
~~~

Update một nickname:

~~~sql
UPDATE profiles_by_id
SET nickname = 'AnN'
WHERE tenant_id = 'T01'
  AND profile_id = 'P01';
~~~

Xóa nickname:

~~~sql
UPDATE profiles_by_id
SET nickname = null
WHERE tenant_id = 'T01'
  AND profile_id = 'P01';
~~~

Trong Cassandra, thao tác set null ở trên có ý nghĩa loại bỏ giá trị nickname, không lưu một BSON Null có thể phân biệt ổn định với missing bằng một index phổ quát. Tùy driver và prepared statement, **UNSET** có semantics “không ghi cột này”, khác explicit null.

### 10.1. Không dùng NULL trong primary key

Các thành phần primary key được yêu cầu để định danh partition/row và không được có giá trị NULL. Không thể dùng primary key NULL để tự tạo một “nhóm các hàng thiếu nickname” theo cách một số người suy từ JSON.

### 10.2. Truy vấn cột bị thiếu không phải access pattern tự nhiên

Một bảng Cassandra chủ yếu phục vụ lookup theo partition/clustering keys. Truy vấn “mọi profile mà nickname bị thiếu” trên hàng triệu partition không tự nhiên là một truy vấn index hiệu quả.

Thay vì giả định có thể dùng một điều kiện **IS NULL** phổ quát như SQL quan hệ, hãy mô hình đường đọc:

~~~text
profiles_by_id:
    (tenantId, profileId) -> profile chính

profiles_by_review_state:
    (tenantId, state, bucket) -> profileId, updatedAt
~~~

Một trạng thái **NO_NICKNAME** hoặc **PROFILE_INCOMPLETE** là **giá trị hợp lệ không NULL**, được lưu ở đường truy cập chuyên dụng.

### 10.3. Tombstones và chi phí truy vấn

Đặt nhiều cột về null, xóa record hoặc dùng TTL có thể tạo tombstone. Tích lũy tombstone gây ảnh hưởng đến đọc, compaction và repair tùy topology/workload. Không nên coi “ghi NULL cho mọi thuộc tính tùy chọn” là cách miễn phí để giữ cấu trúc đồng nhất.

Các secondary index hoặc Storage-Attached Index (SAI) có phạm vi hỗ trợ điều kiện cụ thể theo phiên bản Cassandra. Cần kiểm tra loại cột, toán tử và query plan; không suy rằng một index giúp truy vấn mọi trường hợp missing/null như MongoDB.

## 11. Elasticsearch/OpenSearch: exists nói về giá trị được index

Trong Elasticsearch, toán tử **exists** trong Query DSL dùng để tìm document có **indexed value** cho một field, không đơn giản là kiểm tra JSON nguồn có key đó.

Ví dụ:

~~~json
{"docId":"D1","nickname":"An"}
{"docId":"D2"}
{"docId":"D3","nickname":null}
{"docId":"D4","nickname":[]}
{"docId":"D5","nickname":""}
{"docId":"D6","nickname":[null,"Binh"]}
~~~

Với mapping phù hợp và không có null_value đặc biệt, các trường hợp điển hình:

| Document | JSON field | Có indexed value cho nickname? |
| --- | --- | --- |
| D1 | "An" | Có |
| D2 | Missing | Không |
| D3 | null | Không |
| D4 | [] | Không |
| D5 | "" | **Có** |
| D6 | [null, "Binh"] | **Có** |

Điểm khác MongoDB rất quan trọng: **explicit null trong _source thường không tạo indexed value**, vì vậy exists có thể xem nó như “không có giá trị để tìm kiếm”.

### 11.1. Truy vấn exists

~~~json
GET profiles/_search
{
  "query": {
    "exists": {
      "field": "nickname"
    }
  }
}
~~~

Mẫu này tìm các document có indexed value cho nickname.

### 11.2. Truy vấn không có indexed value

~~~json
GET profiles/_search
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "nickname"
          }
        }
      ]
    }
  }
}
~~~

Đây là tập **không có indexed value**, có thể bao gồm missing, explicit null, empty array, hoặc value đã bị bỏ qua khi indexing. **Không được diễn giải trực tiếp thành “field không tồn tại trong _source”**.

### 11.3. Vì sao JSON có key nhưng exists vẫn false?

Ngoài null hoặc empty array, một field có thể không có indexed value do:

- Mapping cấu hình không index và không có doc values theo trường hợp tương ứng.
- Chuỗi vượt **ignore_above** và bị bỏ qua khỏi index.
- Dữ liệu sai định dạng bị bỏ qua khi **ignore_malformed** được bật.
- Các đặc điểm khác của mapping/kiểu field ảnh hưởng khả năng index.

Vì vậy, phân tích lỗi “trường có trong document nhưng query không tìm thấy” phải xem **mapping, trạng thái indexing và _source**, không chỉ kiểm tra JSON.

### 11.4. null_value mapping

Nếu muốn biến **explicit null** thành một giá trị có thể tìm kiếm trong index, Elasticsearch có tham số **null_value** ở một số loại field phù hợp.

~~~json
PUT profiles_null_index
{
  "mappings": {
    "properties": {
      "nickname": {
        "type": "keyword",
        "null_value": "__NULL_SENTINEL__"
      }
    }
  }
}
~~~

Ghi:

~~~json
POST profiles_null_index/_doc/D3
{
  "nickname": null
}
~~~

Truy vấn:

~~~json
GET profiles_null_index/_search
{
  "query": {
    "term": {
      "nickname": "__NULL_SENTINEL__"
    }
  }
}
~~~

Ý nghĩa:

- Explicit null được **thay bằng sentinel khi lập index**.
- **_source vẫn giữ null**; null_value không sửa payload nguồn.
- **Missing field** không tự tạo sentinel.
- Empty array không được thay giống một explicit scalar null.
- Sentinel phải có cùng loại dữ liệu phù hợp với field mapping.

Nếu dữ liệu người dùng có thể chứa chuỗi **__NULL_SENTINEL__** thật, kết quả term có thể lẫn hai nghĩa. Phải chọn quy ước sentinel không va chạm hoặc dùng **field trạng thái riêng** để phân biệt chắc chắn.

### 11.5. Search schema không phải storage schema

Một document có thể có nickname trong _source nhưng mapping không cho index field này. Đó là lý do việc quyết định trường có thể tìm/search được nằm ở **search mapping**, không chỉ tại ứng dụng gửi JSON.

Trong một pipeline nhiều bản chiếu, source DB và Elasticsearch có thể có semantics missing/null khác nhau. Mapper/indexer phải định nghĩa rõ chuyển đổi, thay vì đơn giản chuyển nguyên source document rồi giả định mọi query giống MongoDB.

## 12. Redis: thiếu key, thiếu hash field và null tự mã hóa

Redis key–value không có một khái niệm secondary index trên mọi trường JSON giống database document.

Hai thao tác khác nhau:

~~~redis
EXISTS profile:T01:P01
~~~

và:

~~~redis
HEXISTS profile:T01:P01 nickname
~~~

- **EXISTS** hỏi một Redis key có tồn tại không.
- **HEXISTS** hỏi field nickname có tồn tại trong hash đó không.

Ví dụ:

~~~redis
HSET profile:T01:P01 name "An" nickname "AnN"
HEXISTS profile:T01:P01 nickname
HDEL profile:T01:P01 nickname
HEXISTS profile:T01:P01 nickname
~~~

Khi dùng hash, một field có giá trị chuỗi rỗng không giống field đã HDEL. Redis hash field không có kiểu BSON Null tự nhiên; nếu application cần explicit null, phải mã hóa theo contract (ví dụ trạng thái riêng), không dùng chuỗi "null" rồi nghĩ nó giống null của MongoDB.

**SCAN** có thể duyệt keyspace phục vụ bảo trì nhưng không tự tạo index theo “nickname không tồn tại” cho hàng triệu profile. Với access pattern thường xuyên, cần một set/sorted set hoặc read model theo trạng thái và cơ chế đồng bộ khi field thay đổi.

## 13. Thiết kế chỉ mục cho trường tùy chọn: quyết định theo truy vấn

Giả sử 5 triệu đơn hàng có trường **assignedAgentId** chỉ xuất hiện ở 8% đơn được phân công.

Các truy vấn:

~~~text
Q1. Tìm đơn đã được giao cho agent A17.
Q2. Tìm mọi đơn chưa được giao cho ai.
Q3. Lấy 20 đơn cần phân công gấp nhất.
Q4. Đếm số đơn không có assignedAgentId theo từng tenant.
~~~

### 13.1. Q1: chỉ mục trên giá trị có mặt

Nếu engine hỗ trợ sparse/partial index và phần đã phân công ít, có thể tạo index trên:

~~~text
(tenantId, assignedAgentId, updatedAt)
~~~

với điều kiện chỉ index bản ghi có assignedAgentId hợp lệ. Lookup một agent có độ chọn lọc cao sẽ được phục vụ tốt.

### 13.2. Q2: missing là nhóm nghiệp vụ cần đọc riêng

Nếu truy vấn missing rất phổ biến, có thể có:

~~~text
assignmentState = UNASSIGNED | ASSIGNED
~~~

và index theo:

~~~text
(tenantId, assignmentState, createdAt)
~~~

hoặc một read model chỉ chứa những đơn **UNASSIGNED**. Đường đọc này phục vụ trực tiếp Q2.

### 13.3. Q3: cần thứ tự ưu tiên

Nếu người vận hành thường lấy 20 đơn UNASSIGNED gấp nhất, thiết kế chỉ mục:

~~~text
group = (tenantId, assignmentState=UNASSIGNED)
order = (priority DESC, createdAt ASC, orderId)
~~~

Một partial index trên trạng thái UNASSIGNED có thể nhỏ hơn index tất cả đơn. Nhưng khi một đơn chuyển từ UNASSIGNED sang ASSIGNED, entry trong partial/read model phải được **gỡ**, và query phải chấp nhận độ trễ của bản chiếu nếu dùng hệ phân tán eventual.

### 13.4. Q4: count trên missing

Đếm số đơn chưa phân công theo tenant có thể được tính trực tiếp từ trạng thái/index; với tải phân tích lớn, một aggregate counter hoặc warehouse read model có thể phù hợp hơn truy vấn quét.

Tuy nhiên, counter dẫn xuất cần xử lý cập nhật/idempotency; nếu người dùng cần con số chính xác ngay để đưa ra quyết định nghiệp vụ, không thể mặc định counter eventual là đủ.

## 14. Chọn sparse, partial hay trạng thái tường minh?

| Tiêu chí | Sparse index | Partial index | Trường trạng thái/index đầy đủ | Read model riêng |
| --- | --- | --- | --- | --- |
| Bản ghi có field hiếm | Phù hợp trong engine hỗ trợ | Phù hợp | Có thể | Có thể |
| Cần loại explicit null | Không mặc định | Tùy filter | Có thể biểu diễn | Có thể |
| Cần lọc theo status=OPEN | Không đủ nếu chỉ xét field tồn tại | Rất phù hợp | Phù hợp | Phù hợp |
| Cần tìm missing thường xuyên | Không cung cấp entry missing | Có thể index điều kiện biểu diễn được | **Phù hợp** | **Phù hợp** |
| Cần query qua nhiều access pattern | Hạn chế theo index keys | Hạn chế theo filter/keys | Tùy chỉ mục | Có thể nhiều bản chiếu |
| Chi phí duy trì khi record đổi trạng thái | Có | Có | Index updates | Đồng bộ liên hệ dữ liệu nguồn |
| Nhất quán đa hệ | Cùng database theo semantics engine | Cùng database theo semantics engine | Cùng database nếu cập nhật atomic | Cần quản lý hội tụ/lag |

### 14.1. Không tự biến NULL thành sentinel khi chưa định nghĩa ý nghĩa

Một quy ước:

~~~text
email = "__MISSING__"
~~~

có thể giúp index trạng thái thiếu, nhưng tạo rủi ro:

- Va chạm với dữ liệu thật.
- Người đọc nhầm sentinel thành email hợp lệ.
- Unique constraint có thể coi mọi khách chưa có email là trùng khóa.
- API vô tình trả sentinel ra ngoài.
- Dữ liệu cũ thiếu field vẫn không có sentinel.

Thường một field trạng thái riêng **emailState** rõ ý nghĩa hơn việc trộn sentinel với miền giá trị email. Nếu buộc dùng sentinel, cần khóa chặt encoding, validator, API mapping và versioning.

### 14.2. Trạng thái boolean có thể quá nghèo

~~~text
hasEmail = true / false
~~~

có thể chưa phân biệt:

~~~text
NOT_PROVIDED
PROVIDED_UNVERIFIED
VERIFIED
BOUNCED
REMOVED_BY_USER
NOT_APPLICABLE
~~~

Nếu workflow cần những trạng thái này, boolean có thể khiến nghiệp vụ suy diễn sai. Mô hình trạng thái cần phản ánh **quy trình thực**, nhưng tránh tạo quá nhiều enum không có trường hợp sử dụng rõ ràng.

## 15. Unique constraint, tính chuẩn hóa và cạnh tranh ghi

### 15.1. “Unique khi có giá trị” cần một hợp đồng chi tiết

Ví dụ:

> Mỗi tenant không có hai user cùng email đã xác minh.

Cần trả lời:

1. Chỉ email **VERIFIED** mới unique, hay cả email đã nhập nhưng chưa verify?
2. Uniqueness theo **tenant** hay toàn hệ thống?
3. So sánh có phân biệt chữ hoa/chữ thường không?
4. Giá trị NULL và missing có được xuất hiện nhiều lần không?
5. Khi user xóa email, index entry cũ có được loại đúng không?
6. Nếu hai request cùng lúc chọn email đó, ai được phép thành công?

Một partial unique index có thể giúp trong cùng database, nhưng chỉ khi filter, key, collation và phạm vi phân tán phù hợp với invariant.

### 15.2. Race condition nếu chỉ kiểm tra trước khi ghi

~~~text
Request A: find(email="an@example.com") -> không có
Request B: find(email="an@example.com") -> không có
Request A: insert -> thành công
Request B: insert -> thành công nếu thiếu unique atomic constraint
~~~

**Check-then-insert ở application không đủ** nếu hai request chạy đồng thời. Cần unique index hoặc conditional write/transaction có bảo đảm cạnh tranh phù hợp.

Trong DynamoDB, nếu uniqueness không trùng chính partition/sort key của base table, có thể cần mô hình **reservation item** hoặc transaction để bảo vệ key duy nhất. Một GSI có tính nhất quán sau cùng không tự chứng minh “find không thấy” có thể dùng để cấp phát tên/email duy nhất.

### 15.3. Empty string có phải email hay không?

Nếu form gửi:

~~~json
{"email":""}
~~~

mà ứng dụng định nghĩa “chưa cung cấp email”, nên **chuẩn hóa tại input boundary** theo contract, ví dụ bỏ field hoặc chuyển thành trạng thái NOT_PROVIDED. Nếu để chuỗi rỗng đi thẳng vào unique index, nhiều hồ sơ có thể bị từ chối vì đụng giá trị "".

Đừng tự động chuyển tất cả false, 0, empty array thành missing; chúng có thể là giá trị nghiệp vụ hợp lệ.

## 16. Tác động tới hiệu năng và Query Planner

Một index thưa có thể giảm:

- Số lượng index entries.
- Dung lượng index trên đĩa.
- Chi phí ghi/duy trì index với các document không tham gia.
- Lượng index phải duyệt khi query chỉ quan tâm nhóm nhỏ.

Nhưng nó có thể tăng:

- Độ phức tạp của mô hình dữ liệu và quy tắc ứng dụng.
- Chi phí chuyển trạng thái vào/ra partial index.
- Rủi ro query dùng index không đầy đủ hoặc hint sai.
- Nhu cầu giữ read model khác cho nhóm missing.
- Chi phí đối soát khi nhiều bản chiếu đồng bộ bất đồng bộ.

### 16.1. Selectivity và tần suất truy vấn

Giả sử:

~~~text
10.000.000 documents
200.000 documents có discountCode (2%)
9.800.000 documents không có discountCode (98%)
~~~

Nếu 90% truy vấn hỏi **discountCode = "NEWUSER"**, index chỉ chứa 2% document có thể hữu ích.

Nếu 90% truy vấn hỏi **discountCode missing**, một sparse index trên discountCode **không phải** đường tối ưu trực tiếp. Tạo một nhóm có index theo trạng thái missing, hoặc đánh giá một full index/aggregation khác sẽ hợp lý hơn.

Không nên dựa chỉ trên tỷ lệ thưa: cần xét **phân phối giá trị trong 2% có field**. Nếu 99% giá trị cùng là "NEWUSER", điều kiện bằng giá trị đó cũng ít chọn lọc trong tập đã index.

### 16.2. Plan thực thi quan trọng hơn suy đoán

Với MongoDB, dùng:

~~~javascript
db.customers
  .find({ email: { $exists: true } })
  .explain("executionStats");
~~~

Các thông số nên quan sát:

- Index nào được chọn.
- Có **IXSCAN** hay **COLLSCAN**.
- Có FETCH để kiểm tra document không.
- **totalKeysExamined**, **totalDocsExamined**.
- **nReturned** và thời gian/độ trễ trên dữ liệu đại diện.

Không mặc định rằng IXSCAN luôn tốt hơn COLLSCAN; với truy vấn trả phần lớn collection, quét tuần tự có thể hợp lý. Cũng không coi một query nhanh trên collection thử nghiệm vài trăm record là bằng chứng hiệu năng với hàng triệu record.

### 16.3. Tính đúng đắn của tập kết quả đứng trước tối ưu hóa

Một planner có thể từ chối sparse/partial index vì nó **không chứa toàn bộ dữ liệu mà query có thể trả**. Đừng ép hint chỉ để có IXSCAN rồi không phát hiện một phần khách hàng đã bị loại khỏi kết quả.

Một bài kiểm tra đúng nên đối chiếu ID kết quả với một cách đọc authoritative trên bộ dữ liệu có **missing, null, empty, false, zero, array và legacy fields**, không chỉ xem tốc độ.

## 17. Schema evolution và dữ liệu legacy

Một schema có thể tiến hóa theo thời gian:

~~~text
V1: luôn ghi email = null khi chưa có
V2: bỏ hẳn email khi chưa có
V3: lưu emailState = NOT_PROVIDED / VERIFIED
~~~

Nếu collection có cả ba phiên bản:

- **{email:null}** và **email missing** khác nhau trong một số query.
- Sparse index đơn trường MongoDB vẫn index record V1 null.
- Partial index theo **email kiểu string** loại cả V1 null và V2 missing.
- Truy vấn theo **emailState** sẽ bỏ sót V1/V2 chưa được backfill.

Không nên đổi writer sang V3 rồi lập tức giả định query theo emailState đã bao phủ mọi record.

### 17.1. Expand – migrate – contract

Một quy trình:

1. **Expand:** reader hiểu V1/V2/V3, định nghĩa rõ “chưa cung cấp” theo từng format.
2. **Introduce state:** writer mới ghi emailState có kiểm soát.
3. **Backfill:** tính emailState cho document cũ theo quy tắc an toàn.
4. **Build index:** tạo index phục vụ access pattern mới; xử lý duplicate trước khi thêm unique.
5. **Compare:** đối chiếu số record và ID giữa query cũ/mới.
6. **Cutover:** chuyển API sang query mới sau khi đạt tiêu chí.
7. **Contract:** ngừng đọc format cũ theo kế hoạch retention/backup phù hợp.

### 17.2. Backfill không được ghi đè cập nhật mới

~~~text
T0: job đọc user U01, email missing, version 5
T1: user nhập email mới, version 6
T2: job ghi emailState=NOT_PROVIDED theo snapshot version 5
~~~

Nếu job cập nhật mù, trạng thái trở nên sai. Cần **conditional write/CAS theo version** hoặc đọc lại trước khi cập nhật, và xử lý conflict bằng retry an toàn.

### 17.3. Các bản chiếu eventual có thể trễ

Nếu emailState được lưu ở database nguồn nhưng hệ search/GSI/read model cập nhật bất đồng bộ, một user mới thêm email có thể vẫn xuất hiện trong danh sách “chưa cung cấp” cho tới khi bản chiếu hội tụ.

Nếu nghiệp vụ dùng danh sách này chỉ để nhắc cập nhật hồ sơ, độ trễ nhỏ có thể chấp nhận. Nếu dùng nó để quyết định bảo mật hoặc cấp quyền, phải kiểm tra nguồn có thẩm quyền tại điểm quyết định.

## 18. Trường hợp nested document và array

### 18.1. Missing ở đường dẫn lồng nhau

Hai document:

~~~json
{"profile":{"contact":{"email":"an@example.com"}}}
{"profile":{"contact":{}}}
~~~

Một query theo đường dẫn **profile.contact.email** cần xét sự hiện diện của các parent object. Nếu profile hoặc contact thiếu hoàn toàn, đường dẫn sâu cũng không có giá trị để index.

Với MongoDB:

~~~javascript
db.users.find({
  "profile.contact.email": { $exists: false }
});
~~~

Query có thể khớp document thiếu email, thiếu contact hoặc thiếu profile. Nếu nghiệp vụ muốn “profile tồn tại, contact tồn tại, nhưng email chưa có”, cần thêm điều kiện/trạng thái để phân biệt.

### 18.2. Array rỗng khác mảng có null

~~~json
{"tags":[]}
{"tags":[null]}
{"tags":["nosql"]}
~~~

Trong MongoDB, field **tags** hiện diện ở cả ba document, nhưng multikey index và các toán tử truy vấn có semantics riêng về phần tử array. Trong Elasticsearch, empty array thường không tạo indexed value, còn array có một giá trị thật thì có thể tạo.

Đừng áp bảng truth table của **scalar email** nguyên xi cho array; cần thiết kế test riêng cho mảng rỗng, mảng null, mảng lồng nhau và các phần tử khác kiểu.

### 18.3. Nhiều field tùy chọn trong compound index

Giả sử:

~~~text
(tenantId, region, nickname, createdAt)
~~~

Nếu region và nickname đều optional, cần xác định:

- Thứ tự key ảnh hưởng query tiền tố thế nào.
- Các document thiếu một thành phần có được index không.
- Unique constraint áp dụng trên tuple nào.
- Có hỗ trợ sort theo createdAt khi bỏ điều kiện nickname không.
- Phạm vi index có bao phủ mọi document của truy vấn không.

Không nên thêm một compound index lớn với nhiều field optional rồi kỳ vọng tất cả access pattern đều hiệu quả.

## 19. Vận hành: index nhỏ vẫn có thể gây lỗi lớn

### 19.1. Dữ liệu sai kiểu

Nếu email có thể là number:

~~~json
{"email":12345}
~~~

một partial unique index chỉ lọc string sẽ **không phát hiện duplicate** cho record sai kiểu. Cần validator hoặc application schema rõ ràng. Index chỉ bảo đảm trên tập record nó bao phủ.

### 19.2. Xóa/TTL và trạng thái dẫn xuất

Nếu user xóa email, phải:

- Xóa/đổi trường nguồn theo contract.
- Cập nhật emailState.
- Gỡ entry trong index hoặc GSI.
- Cập nhật read model/analytics nếu có.
- Không để một sự kiện cũ thêm lại email sau thao tác xóa.

Trong Cassandra, xóa cột có thể tạo tombstone; trong DynamoDB, GSI cập nhật bất đồng bộ; trong Elasticsearch, thao tác xóa/refresh có độ trễ riêng. Một thao tác xóa ở nguồn không có nghĩa mọi bản dẫn xuất đã hoàn tất ngay.

### 19.3. Privacy: missing không đủ chứng minh dữ liệu đã được xóa

Một API trả document không có email không chứng minh email không còn nằm trong search index, cache, log hoặc backup. Ngược lại, query trên search không thấy email có thể do mapping không index, chứ không phải dữ liệu đã được loại khỏi _source.

Nếu yêu cầu là xóa dữ liệu cá nhân, phải có quy trình theo dõi mọi bản sao và chính sách retention; không dùng **$exists:false** hoặc **must_not exists** làm bằng chứng xóa vật lý toàn hệ.

### 19.4. Index build và thay đổi online

Tạo unique/partial index trên tập dữ liệu lớn cần:

- Xác minh dữ liệu hiện có thỏa ràng buộc.
- Đo chi phí build, I/O, write amplification và tác động latency.
- Chọn thời điểm/quy trình migration phù hợp.
- Giám sát index build và plan của query sau cutover.
- Có rollback và phương án xử lý duplicate legacy.

Không nên tự xóa dữ liệu trùng để “build index cho nhanh” khi chưa hiểu bản ghi nào có thẩm quyền.

## 20. Quy trình thiết kế index cho dữ liệu thưa

### Bước 1 — Viết đúng ngữ nghĩa nghiệp vụ

Hỏi:

~~~text
Missing nghĩa là gì?
Explicit NULL nghĩa là gì?
"" có hợp lệ không?
false và 0 có phải giá trị hợp lệ không?
Array [] khác field vắng mặt ra sao?
Trạng thái này có thể thay đổi qua những thao tác nào?
~~~

Nếu không trả lời được, đừng chọn sparse index trước.

### Bước 2 — Liệt kê access pattern

Viết chính xác:

~~~text
Q1: tìm customer theo email
Q2: lọc customer chưa có email theo tenant
Q3: lấy các ticket OPEN theo updatedAt DESC
Q4: đếm hồ sơ thiếu email mỗi ngày
~~~

Nêu tần suất, kích thước dữ liệu, latency và số record cần trả.

### Bước 3 — Đo phân bố dữ liệu

Tính:

- Tỷ lệ missing.
- Tỷ lệ explicit null.
- Tỷ lệ empty string/array.
- Phân phối các giá trị hợp lệ.
- Tỷ lệ bản ghi sai type hoặc legacy.
- Tần suất cập nhật khiến record đi vào/ra index.

### Bước 4 — Chọn đường truy cập

- Tìm field đã có và hiếm: cân nhắc sparse hoặc partial index.
- Tìm nhóm trạng thái rõ: partial index theo trạng thái.
- Tìm missing thường xuyên: lưu explicit state/index trên nhóm missing hoặc read model.
- Unique khi có giá trị: unique partial/sparse với ngữ nghĩa null/missing chính xác.
- Truy vấn ad hoc hiếm: scan/analytics có kiểm soát có thể hợp lý.

### Bước 5 — Thiết kế schema và ràng buộc

Chọn kiểu dữ liệu chuẩn, validator, nullable policy, tenant scope, normalization và concurrency. Nếu cần GSI/denormalization, xác định nguồn authoritative và cơ chế cập nhật.

### Bước 6 — Kiểm tra query đầy đủ kết quả

Tạo dữ liệu có:

~~~text
missing, explicit NULL, empty string,
false, zero, empty array, array chứa NULL,
giá trị thật, field sai type, bản ghi legacy
~~~

So sánh ID query với kết quả mong đợi; đừng dùng hint ép sparse index khi nó thiếu document.

### Bước 7 — Đo query plan, cost và lag

Quan sát query plan, keys/docs examined, I/O, index size, update cost và độ trễ GSI/search read model. Tính cả p95/p99 và tải đồng thời, không chỉ benchmark một query nhỏ.

### Bước 8 — Triển khai migration an toàn

Cho reader hỗ trợ format cũ/mới, backfill bằng conditional write, tạo index, chuyển traffic rồi mới gỡ logic legacy.

### Bước 9 — Giám sát sau deploy

Theo dõi schema drift, duplicate key errors, partial-index selectivity, data mismatch và lag của bản chiếu. Có job reconciliation nếu dữ liệu dẫn xuất có thể sai lệch.

## 21. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Coi missing và null luôn giống nhau | Truy vấn thiếu/thừa document | Định nghĩa ngữ nghĩa theo engine |
| Coi "" là null | Unique constraint hoặc filter sai | Chuẩn hóa input có chủ đích |
| Coi false/0 là missing | Mất dữ liệu hợp lệ | Tách value và absence |
| MongoDB {f:null} chỉ được hiểu là explicit null | Kết quả gồm cả missing | Dùng $type hoặc điều kiện phân biệt |
| Sparse MongoDB bỏ cả null | Unique sparse có thể lỗi | Nhớ sparse đơn trường vẫn index explicit null |
| Ép hint trên sparse index không đủ | Trả kết quả thiếu | Để planner chọn index đúng; kiểm chứng độ đầy đủ |
| Compound sparse được coi là “mọi field phải có” | Index lớn hơn dự kiến | Kiểm tra quy tắc compound |
| Partial index nhưng query không hàm ý filter | Planner không dùng hoặc kết quả thiếu nếu ép | Viết query phù hợp index |
| GSI key dùng NULL/empty | Không tạo item index như mong muốn hoặc lỗi validation | Bỏ key attribute khi không tham gia |
| Query DynamoDB thiếu PK rồi dùng FilterExpression | Scan/đọc rộng, tốn tài nguyên | Thiết kế GSI theo access pattern |
| Elasticsearch exists được hiểu là key trong _source | Nhầm null/ignored value với missing | Kiểm tra mapping và indexed value |
| Dùng null_value sentinel không chống va chạm | Lẫn NULL với giá trị thật | Quy ước trạng thái tường minh |
| Cassandra ghi null để “lưu placeholder” | Xóa cell/tạo tombstone | Hiểu null/unset và mô hình state |
| Check uniqueness chỉ bằng một lệnh read trước insert | Race khi ghi đồng thời | Atomic unique/conditional write |
| Backfill trạng thái không có version check | Ghi đè cập nhật mới | CAS, retry, reconcile |
| Dùng index để chứng minh dữ liệu đã xóa vật lý | Bỏ sót cache/source/backup | Xây quy trình deletion riêng |

## 22. Bài tập thực hành

### Bài 1 — Phân biệt năm document

Cho:

~~~json
{"_id":"A","email":"a@example.com"}
{"_id":"B"}
{"_id":"C","email":null}
{"_id":"D","email":""}
{"_id":"E","email":"e@example.com"}
~~~

**Câu hỏi:** Trong MongoDB, truy vấn email bằng null trả ID nào? Truy vấn $exists:false trả ID nào? Truy vấn $exists:true trả ID nào?

**Gợi ý:** {email:null} trả B,C; $exists:false trả B; $exists:true trả A,C,D,E.

### Bài 2 — Sparse index chứa ai?

Trên dữ liệu Bài 1, tạo:

~~~javascript
db.customers.createIndex(
  { email: 1 },
  { sparse: true }
);
~~~

**Câu hỏi:** Document nào không tạo entry? Document email:null có được index không?

**Gợi ý:** B không có entry. C vẫn có entry vì field email hiện diện dù value null.

### Bài 3 — Unique sparse và NULL

Collection có nhiều user thiếu email. Thêm unique sparse index trên email, sau đó thêm hai user có email:null.

**Câu hỏi:** Hai user thiếu email có thể cùng tồn tại không? Hai user explicit null thì sao?

**Gợi ý:** Nhiều user thiếu field có thể tồn tại. Hai explicit null thường gây duplicate key với unique sparse đơn trường.

### Bài 4 — Partial index theo kiểu

Ứng dụng chỉ muốn index email khi email là string:

~~~javascript
partialFilterExpression: {
  email: { $type: "string" }
}
~~~

**Câu hỏi:** Missing, null, "" và "a@example.com" có được index không?

**Gợi ý:** Missing và null không; hai string còn lại có. Nếu "" không được phép, phải validate/chuẩn hóa hoặc lọc theo quy tắc bổ sung.

### Bài 5 — Planner và kết quả thiếu

Một sparse index bỏ qua document thiếu email. Lập trình viên dùng hint để chạy:

~~~javascript
db.customers.find({}).hint("email_sparse_idx");
~~~

**Câu hỏi:** Vì sao có thể sai mặc dù query chạy nhanh?

**Gợi ý:** Truy vấn yêu cầu mọi customer nhưng sparse index không chứa document thiếu email; hint có thể buộc quét index không đầy đủ.

### Bài 6 — Sparse GSI trong DynamoDB

GSI1 có key **GSI1PK/GSI1SK**. Item A có đầy đủ hai key, item B thiếu GSI1SK, item C thiếu cả hai.

**Câu hỏi:** Item nào xuất hiện trong GSI1?

**Gợi ý:** Chỉ A, nếu các giá trị khóa hợp lệ. Item thiếu một khóa bắt buộc không tạo entry.

### Bài 7 — DynamoDB explicit NULL

Một item có:

~~~json
{"email": null}
~~~

Ở DynamoDB, ứng dụng biểu diễn explicit NULL bằng AttributeValue kiểu NULL.

**Câu hỏi:** attribute_exists(email) và attribute_not_exists(email) nói gì? Có thể dùng NULL làm GSI key không?

**Gợi ý:** Attribute có mặt nên tồn tại theo điều kiện kiểm tra sự hiện diện; NULL không phải kiểu hợp lệ cho GSI key. Nếu muốn item không tham gia GSI, bỏ key attribute theo thiết kế.

### Bài 8 — Elasticsearch exists

Cho:

~~~json
{"nickname":null}
{"nickname":[]}
{"nickname":""}
{"nickname":[null,"An"]}
~~~

**Câu hỏi:** Với mapping keyword thông thường và không có null_value, exists nickname khớp những dòng nào?

**Gợi ý:** Chuỗi rỗng và mảng có "An" là những trường hợp có indexed value; null và empty array thường không tạo indexed value.

### Bài 9 — Tìm nhóm chưa được giao việc

Có một triệu task, chỉ 5% đã có assignedAgentId. Màn hình vận hành thường lấy 50 task UNASSIGNED mới nhất.

**Câu hỏi:** Sparse index assignedAgentId có phục vụ truy vấn này trực tiếp không? Thiết kế nào phù hợp hơn?

**Gợi ý:** Index chỉ chứa task đã assigned không trực tiếp tìm 95% missing. Cân nhắc assignmentState=UNASSIGNED, index theo (tenantId, state, createdAt) hoặc read model riêng cho tập chưa giao.

### Bài 10 — Cassandra NULL và tombstone

Trong Cassandra, update nickname = null trên một cột không thuộc primary key.

**Câu hỏi:** Có nên hiểu là lưu một giá trị NULL như BSON Null? Chi phí nào cần quan sát?

**Gợi ý:** CQL NULL thường mang nghĩa xóa giá trị/cell, có thể sinh tombstone. Cần chú ý đọc và compaction; dùng trạng thái riêng nếu nghiệp vụ cần phân biệt “chưa cung cấp” với “đã xóa”.

### Bài 11 — Migration từ NULL sang missing

V1 lưu email:null khi thiếu, V2 bỏ field, V3 ghi emailState. Trong lúc rollout, một job backfill đọc user version 4 rồi user tự thêm email version 5.

**Câu hỏi:** Làm sao tránh job gán sai emailState=NOT_PROVIDED?

**Gợi ý:** Conditional write dựa trên version, phát hiện conflict, đọc lại và áp dụng logic phù hợp. Query V3 phải có chiến lược bao phủ dữ liệu legacy trước khi chuyển hoàn toàn.

### Bài 12 — Uniqueness theo tenant

Yêu cầu: email VERIFIED phải unique trong tenant, nhưng hai tenant khác nhau có thể dùng cùng email; email chưa VERIFIED có thể tồn tại nhiều lần theo chính sách.

**Câu hỏi:** Cần những thành phần nào?

**Gợi ý:** Compound key gồm tenant và email chuẩn hóa, filter điều kiện VERIFIED, atomic unique constraint hoặc reservation/transaction phù hợp, cùng validator/authorization. Không dựa vào kiểm tra đọc trước ghi trên read model eventual.

## 23. Gợi ý tài liệu kỹ thuật khi áp dụng vào sản phẩm thật

Các điểm cần đối chiếu tài liệu chính thức của **phiên bản đang triển khai**:

- MongoDB: [Sparse indexes](https://www.mongodb.com/docs/manual/core/index-sparse/) và [Partial indexes](https://www.mongodb.com/docs/manual/core/index-partial/).
- AWS DynamoDB: [Sparse indexes for GSIs](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-indexes-general-sparse-indexes.html).
- Elasticsearch: [Exists query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-exists-query) và [null_value mapping](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/null-value).

Các tài liệu trên mô tả những cơ chế **khác nhau**, không nên lấy cú pháp hoặc ngữ nghĩa từ một hệ rồi áp cho hệ khác. Với Cassandra và Redis, cũng cần tra phiên bản CQL/driver/client và khả năng secondary index thực tế trước khi đưa câu truy vấn vào production.

## 24. Kết luận

**Dữ liệu thưa không chỉ là bài toán tiết kiệm dung lượng index; đó là bài toán biểu diễn trạng thái và xác định tập kết quả chính xác.** Trường không tồn tại, explicit NULL, chuỗi rỗng, số 0, false và mảng rỗng có thể mang ý nghĩa nghiệp vụ khác nhau, đồng thời được từng engine lưu và lập chỉ mục theo cách khác nhau.

Trong MongoDB, **sparse index đơn trường bỏ qua missing nhưng vẫn index explicit null**; **partial index** cho phép xác định tập được index bằng điều kiện rõ hơn. Trong DynamoDB, **GSI thưa** thường được tạo bằng cách bỏ thuộc tính khóa index ở các item không tham gia. Trong Cassandra, **NULL thường biểu thị xóa cell và có thể sinh tombstone**; còn ở Elasticsearch, **exists kiểm tra indexed value chứ không đơn giản kiểm tra khóa trong _source**.

Hãy bắt đầu từ **ngữ nghĩa dữ liệu và access pattern**, sau đó chọn index phù hợp, đặt unique/conditional write đúng phạm vi, đo query plan và kiểm tra cả trường hợp missing/null/legacy. Nếu truy vấn trên **tập dữ liệu thiếu trường** là tính năng nóng, mô hình **trạng thái tường minh hoặc bản chiếu chuyên dụng** thường rõ ràng và dễ tối ưu hơn việc cố dùng một sparse index vốn chỉ chứa các bản ghi **có** thuộc tính.
