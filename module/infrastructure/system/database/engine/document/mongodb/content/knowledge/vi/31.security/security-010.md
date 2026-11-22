# Giới hạn truy vấn, index và tính năng khi mã hóa trường trong MongoDB

Một ứng dụng có thể cần lưu thông tin rất nhạy cảm như **số định danh cá nhân, số tài khoản, mức lương, địa chỉ, hồ sơ khách hàng hoặc nội dung hợp đồng** trong MongoDB. Nếu chỉ bật mã hóa ổ đĩa, dữ liệu được bảo vệ ở tầng lưu trữ nhưng tiến trình database vẫn xử lý các giá trị có thể đọc được sau khi giải mã tại server. Trong nhiều hệ thống, yêu cầu bảo mật khắt khe hơn là **giá trị nhạy cảm phải được mã hóa ở phía ứng dụng, trước khi gửi tới MongoDB**.

MongoDB cung cấp hai hướng mã hóa trường khi dữ liệu đang được sử dụng (in-use encryption) thường gặp:

- **Client-Side Field Level Encryption (CSFLE)**, có kiểu mã hóa *deterministic* hoặc *randomized*.
- **Queryable Encryption (QE)**, sử dụng kỹ thuật hỗ trợ các kiểu truy vấn đã khai báo trên dữ liệu mã hóa mà không cần cho server thấy plaintext.

Nhưng **mã hóa thay đổi khả năng truy vấn**. Một trường ở dạng ciphertext không còn đương nhiên hỗ trợ tìm kiếm từ khóa, so sánh lớn hơn/nhỏ hơn, sắp xếp, tính trung bình, tạo unique index hoặc dùng làm shard key như trường thông thường. Khả năng được phép phụ thuộc loại mã hóa, phiên bản MongoDB, driver, cấu hình khóa và loại truy vấn đã bật từ đầu.

Bài học này giải thích chi tiết những giới hạn đó, cách chọn thiết kế dữ liệu và cách tránh các sai lầm thường gặp khi áp dụng mã hóa trường trong MongoDB.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **TLS, encryption at rest, CSFLE và Queryable Encryption**.
2. Hiểu vì sao server lưu **BinData ciphertext**, không tự so sánh được ý nghĩa plaintext.
3. Phân biệt **deterministic** và **randomized** của CSFLE.
4. Biết những loại query được hỗ trợ bởi **Queryable Encryption** theo phiên bản và **queryType**.
5. Giải thích vì sao **B-tree/unique/text/vector/TTL indexes** không thể tùy tiện áp dụng cho encrypted fields.
6. Nhận diện các hạn chế với **aggregation, sort, group, lookup, update, upsert, null, array, collation, sharding, view và time series**.
7. Thiết kế schema có **các trường định tuyến/lọc thông thường** và **các trường bí mật được mã hóa**, không phá vỡ yêu cầu quyền riêng tư.
8. Xây dựng truy vấn qua **MongoDB driver đã cấu hình mã hóa**, không gửi plaintext thẳng cho một client không có cấu hình phù hợp.
9. Lập kế hoạch về **key management, metadata/index overhead, migration, monitoring, backup và kiểm thử**.

**Phạm vi phiên bản:** MongoDB tiếp tục phát triển Queryable Encryption. Các phiên bản cũ có thể chỉ hỗ trợ equality, hoặc equality + range; các kiểu prefix/suffix/substring đã xuất hiện ở dạng preview trên MongoDB 8.2 và được công bố **GA trong MongoDB 9.0** vào tháng 9/2026. Vì vậy, mọi ví dụ phải được kiểm tra với **server version, driver version, Automatic Encryption Shared Library và FCV** của deployment thực tế. Không áp dụng mặc định cú pháp/tính năng của MongoDB mới lên một cluster 6.x hoặc 7.x.

## 2. Mã hóa ở những tầng nào?

### 2.1. TLS bảo vệ đường truyền

TLS mã hóa lưu lượng giữa các đầu cuối kết nối:

~~~text
Application  ===== TLS connection =====>  MongoDB
~~~

Nó giúp chống đọc trộm hoặc sửa đổi dữ liệu trên đường truyền khi được cấu hình và xác minh đúng. Nhưng **TLS không có nghĩa server không biết plaintext** khi server nhận và xử lý giá trị đã giải mã ở đầu kết nối.

### 2.2. Encryption at rest bảo vệ dữ liệu lưu trữ

Mã hóa dữ liệu ở tầng lưu trữ bảo vệ file/snapshot/ổ đĩa khi những đối tượng đó bị truy cập ngoài kiểm soát. Tuy nhiên, một tiến trình MongoDB được cấp quyền thích hợp vẫn có thể xử lý **giá trị plaintext** của field thông thường sau khi dữ liệu được đọc và giải mã ở tầng storage.

### 2.3. Client-side field encryption bảo vệ giá trị trước khi gửi

~~~text
Application
  |
  |  plaintext: "ID-123456789"
  v
MongoDB Driver + encryption configuration + keys
  |
  |  ciphertext: BinData(...)
  v
MongoDB Server
  |
  |  Stores ciphertext and related metadata
  v
Database files, replication, backups
~~~

Khi đọc:

~~~text
MongoDB Server -> ciphertext BinData(...)
                          |
                          v
             Authorized Driver + keys
                          |
                          v
               plaintext in application
~~~

Nếu client không có khóa/cấu hình giải mã phù hợp, nó có thể chỉ thấy ciphertext, ngay cả khi có quyền đọc MongoDB collection.

**Kết luận:** chỉ sử dụng một trong TLS, encryption at rest hoặc field encryption không tự thay thế toàn bộ các lớp bảo vệ còn lại. Phải kết hợp xác thực, phân quyền, quản lý khóa và kiểm soát logs/backups.

### 2.4. Mô hình đe dọa (threat model)

Client-side encryption có thể giảm nguy cơ lộ plaintext khi kẻ tấn công đọc được dữ liệu từ server, ổ đĩa hoặc database backup nhưng **không có khóa giải mã**.

Nó **không tự bảo vệ** khi:

- Máy ứng dụng đang giữ khóa bị chiếm quyền.
- Process có quyền giải mã cố ý xuất plaintext.
- API trả dữ liệu nhạy cảm cho người dùng không có quyền.
- Secret manager hoặc KMS credentials bị lộ.
- Ứng dụng ghi plaintext vào log, trace, cache hoặc export.
- Một truy vấn trên field công khai để lộ thông tin riêng tư qua metadata.

Vì vậy, bảo vệ field không có nghĩa **mọi thành phần hệ thống** không còn khả năng rò rỉ dữ liệu.

## 3. Ba chế độ mã hóa cần phân biệt

### 3.1. CSFLE deterministic

Với cùng khóa, cùng kiểu và cùng giá trị đầu vào, deterministic encryption tạo **ciphertext ổn định** theo quy tắc thuật toán.

~~~text
"acct-123" --encrypt K--> Ciphertext A
"acct-123" --encrypt K--> Ciphertext A
"acct-999" --encrypt K--> Ciphertext B
~~~

Ưu điểm quan trọng: driver có thể mã hóa **giá trị literal trong truy vấn equality** thành ciphertext tương ứng, và database so sánh ciphertext với các bản ghi đã lưu.

**Đánh đổi bảo mật:** các giá trị trùng nhau tạo ciphertext trùng nhau. Với những field có rất ít giá trị (chẳng hạn giới tính, trạng thái có ba nhãn, nhóm điểm tín dụng), người quan sát ciphertext có thể thực hiện **frequency analysis** và suy luận về phân bố dữ liệu. Vì thế không nên xem deterministic encryption là lựa chọn an toàn mặc định cho mọi trường bí mật.

### 3.2. CSFLE randomized

Với cùng giá trị và khóa, mỗi lần mã hóa thông thường tạo ciphertext khác nhau:

~~~text
"acct-123" --encrypt K--> Ciphertext R1
"acct-123" --encrypt K--> Ciphertext R2
"acct-123" --encrypt K--> Ciphertext R3
~~~

Điều này che giấu sự trùng lặp theo ciphertext tốt hơn deterministic, nhưng MongoDB **không thể dùng equality ciphertext trực tiếp** để xác định bản ghi có cùng giá trị plaintext.

Randomized CSFLE phù hợp cho field chỉ cần **lưu/đọc sau khi giải mã**; ứng dụng truy vấn theo một field khác rồi lấy field mã hóa về client.

### 3.3. Queryable Encryption (QE)

QE hướng tới việc **cho phép một số kiểu truy vấn trên encrypted fields** mà không dùng deterministic ciphertext trùng nhau cho cùng plaintext.

~~~text
Application + QE-enabled Driver
       |    encrypt value and query payload
       v
MongoDB:
  ciphertext encrypted fields
  internal encrypted query metadata/tags
       |
       v
  query engine finds matching candidates
       |
       v
Driver decrypts result for authorized caller
~~~

QE tạo ciphertext có tính ngẫu nhiên, kể cả khi plaintext giống nhau, và dựa vào cơ chế **encrypted index/metadata** dành cho queryType đã cấu hình.

Không thể coi QE đơn giản là CSFLE deterministic được đổi tên. Kiểu truy vấn, index, metadata collections, chi phí ghi, cách tạo collection và các giới hạn khác nhau.

### 3.4. Bảng so sánh tổng quát

| Thuộc tính | CSFLE deterministic | CSFLE randomized | Queryable Encryption |
|---|---|---|---|
| Cùng plaintext cho ciphertext giống nhau? | Có trong cùng điều kiện mã hóa | Không theo thiết kế | Không theo thiết kế |
| Equality trên encrypted field | Có, khi driver/query được cấu hình hợp lệ | Không | Có nếu queryType hỗ trợ equality hoặc range |
| Range trên encrypted field | Không biểu diễn đúng thứ tự plaintext | Không | Có nếu bật queryType range và phiên bản hỗ trợ |
| Prefix/suffix/substring | Không | Không | Theo phiên bản và queryType string được hỗ trợ |
| Mã hóa field nhưng không cho query | Có | Có | Có với queryType none |
| Chỉ số thông thường trên ciphertext | Có thể phục vụ mô hình deterministic equality theo điều kiện phù hợp | Không mang ngữ nghĩa plaintext | Không tạo B-tree index trên encrypted field để thay encrypted index |
| Unique plaintext theo index thông thường | Không phải bảo đảm chung cho mọi thiết kế; phải đánh giá kỹ | Không | Không bảo đảm với encrypted field |
| Server thấy plaintext? | Không, nếu dữ liệu đi qua đường mã hóa đúng | Không, nếu đúng | Không, nếu đúng |
| Chi phí metadata query chuyên biệt | Ít hơn QE nhưng cần đánh giá index | Thường không query trên field | QE có metadata collections/tags và chi phí quản lý riêng |

## 4. Vì sao mã hóa ảnh hưởng query?

Một query bình thường:

~~~javascript
db.employees.find({ salary: { $gt: 50000 } });
~~~

đòi hỏi MongoDB so sánh **giá trị số** và tìm tài liệu có salary lớn hơn 50000.

Khi salary được mã hóa bằng CSFLE, server chỉ lưu đại loại:

~~~javascript
{
  salary: BinData(/* encrypted payload */)
}
~~~

MongoDB không thể kết luận ciphertext nào ứng với salary 60000 chỉ bằng cách so sánh **thứ tự byte** với ciphertext của 50000. Thứ tự ciphertext không phản ánh thứ tự plaintext.

Một trường được mã hóa cũng không còn là String thông thường đối với các phép:

~~~javascript
{ email: /@example\.com$/ }
{ salary: { $gte: 50000 } }
{ name: { $regex: "^Nguyen" } }
{ $expr: { $add: ["$salary", 500] } }
~~~

Các truy vấn này chỉ có thể đúng **nếu một tính năng mã hóa cho phép kiểu truy vấn đó rõ ràng**; không thể tự suy luận rằng mọi query trên plaintext sẽ hoạt động giống hệt.

### 4.1. “Lệnh chạy không lỗi” vẫn có thể trả kết quả sai

Đặc biệt với **explicit/manual encryption**, server có thể áp dụng toán tử lên ciphertext BinData theo ngữ nghĩa BSON. Ví dụ so sánh **$gt** giữa hai ciphertext có thể chạy ở tầng server nhưng kết quả **không phải so sánh lương plaintext**.

Các driver có **automatic encryption** cố gắng chặn nhiều thao tác không hỗ trợ. Không nên cố né giới hạn bằng cách tự mã hóa một literal rồi gửi phép so sánh phạm vi trực tiếp tới server.

### 4.2. Truy vấn trên field chưa mã hóa vẫn hữu ích

Một document có thể lưu:

~~~javascript
{
  tenantId: "TENANT-A",
  recordId: "REC-1001",
  status: "ACTIVE",
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  identity: {
    nationalId: BinData(/* encrypted */)
  },
  salary: BinData(/* encrypted */)
}
~~~

Ứng dụng có thể tìm theo **tenantId**, **recordId**, **status**, **createdAt** khi các trường đó không mã hóa và được index phù hợp; sau đó driver có khóa giải mã **nationalId** và **salary**.

Tuy nhiên, lưu status hoặc createdAt rõ ràng cũng **tiết lộ các metadata đó** cho ai có quyền đọc server. Đây là một **quyết định threat model** cần phê duyệt, không phải cách né mã hóa vô hại.

## 5. Giới hạn truy vấn với CSFLE deterministic

Trong chế độ automatic CSFLE, driver phân tích query, mã hóa các literal được hỗ trợ và giải mã kết quả phù hợp. Với trường **deterministically encrypted**, các operator so sánh được hỗ trợ trong tài liệu MongoDB bao gồm:

- **$eq**, **$ne**.
- **$in**, **$nin**.
- Các tổ hợp **$and**, **$or**, **$not**, **$nor** trong điều kiện được hỗ trợ.
- **$exists** xử lý việc trường có tồn tại; nó không so sánh nội dung plaintext.

Không nên suy ra từ danh sách này rằng **mọi loại BSON** hoặc mọi phép lồng sâu đều tương thích. Ví dụ, automatic CSFLE có các hạn chế về field kiểu array/object, bool, decimal/double trong so sánh deterministic và việc so sánh với null/regex.

### 5.1. Equality dùng driver có cấu hình CSFLE

Ví dụ ứng dụng đã có collection **customers** và **MongoClient được cấu hình automatic CSFLE** để mã hóa field **identity.taxId** bằng deterministic algorithm.

Code query logic:

~~~javascript
// Được thực thi bởi một client đã cấu hình auto encryption.
const result = await encryptedCollection.findOne({
  "identity.taxId": "TAX-000123"
});
~~~

Driver có thể mã hóa literal **TAX-000123** trước khi gửi query, server so sánh ciphertext và driver giải mã field trong kết quả khi có quyền.

**Không thể mặc định chạy lệnh này từ một mongosh không có cấu hình encryption và mong nhận được kết quả**, vì server không tự mã hóa literal plaintext trong query.

### 5.2. $in với nhiều giá trị

~~~javascript
// Chỉ minh họa query từ client automatic CSFLE đã cấu hình.
await encryptedCollection.find({
  "identity.taxId": {
    $in: ["TAX-000123", "TAX-000987"]
  }
}).toArray();
~~~

Các giá trị plaintext trong danh sách cần được driver xử lý đúng schema/algorithm. Kiểu dữ liệu không tương thích, trộn null hoặc query vào field randomized sẽ không mang lại khả năng matching như dự kiến.

### 5.3. $exists không phải tìm theo giá trị

~~~javascript
await encryptedCollection.find({
  "identity.taxId": { $exists: true }
}).toArray();
~~~

Server có thể kiểm tra field tồn tại mà không cần biết plaintext. Nhưng **$exists: true** không giúp phân biệt giá trị "TAX-000123" với "TAX-000987".

### 5.4. Không dùng $gt hoặc $sort để so sánh salary deterministic

~~~javascript
// KHÔNG diễn đạt so sánh plaintext đúng với CSFLE deterministic:
await encryptedCollection.find({
  salary: { $gt: 50000 }
}).toArray();
~~~

~~~javascript
// Không có bảo đảm sắp xếp theo salary plaintext:
await encryptedCollection.find()
  .sort({ salary: -1 })
  .toArray();
~~~

Nếu muốn salary range query ở phía server mà vẫn giữ salary mã hóa, cần nghiên cứu **Queryable Encryption queryType range** và các hạn chế của nó, hoặc đổi thiết kế sao cho không cần range query trên salary.

### 5.5. $regex và collation

~~~javascript
// Không được CSFLE deterministic hỗ trợ như regexp trên plaintext:
await encryptedCollection.find({
  "identity.taxId": /^TAX-00/
}).toArray();
~~~

Việc bật collation **case-insensitive** cũng không làm server giải mã ciphertext để so sánh chuỗi. Nếu có yêu cầu so sánh không phân biệt dấu/chữ hoa trong CSFLE equality, ứng dụng có thể **chuẩn hóa input trước khi mã hóa** trong phạm vi hợp đồng nghiệp vụ đã chấp thuận.

Ví dụ chuẩn hóa email về một quy tắc nhất quán có thể hữu ích cho lookup, nhưng **không tự khẳng định có thể lowercase mọi email/user identifier** mà không ảnh hưởng danh tính. Phải xác định quy tắc normalization đúng nghiệp vụ trước khi áp dụng.

### 5.6. Tại sao deterministic không thích hợp cho field ít giá trị?

Ví dụ một trường encrypted:

~~~text
employmentStatus:
  ACTIVE  -> 95%
  LEAVE   ->  4%
  ENDED   ->  1%
~~~

Nếu deterministic ciphertext trùng nhau cho những giá trị giống nhau, người có thể thống kê ciphertext sẽ thấy ba nhóm có tỷ lệ tương ứng. Họ có thể suy luận nhóm phổ biến nhất là ACTIVE dựa vào thông tin phụ.

Phải đánh giá **cardinality**, khả năng frequency analysis và giá trị thật của field, không mặc định equality performance quan trọng hơn mọi yêu cầu riêng tư.

## 6. Giới hạn truy vấn với CSFLE randomized

Với randomized encryption, cùng plaintext có thể sinh ciphertext khác nhau. Do vậy **không thể tìm equality trực tiếp trên encrypted field bằng query thông thường**.

### 6.1. Ví dụ field không cần truy vấn

Một document:

~~~javascript
{
  _id: "EMP-1001",
  tenantId: "TENANT-A",
  publicEmployeeCode: "E-1001",
  medicalNote: BinData(/* randomized CSFLE ciphertext */)
}
~~~

Ứng dụng đọc:

~~~javascript
// Query theo field không mã hóa:
const employee = await encryptedCollection.findOne({
  tenantId: "TENANT-A",
  publicEmployeeCode: "E-1001"
});

// Nếu driver có quyền và khóa, field medicalNote sẽ được giải mã.
~~~

**medicalNote** được bảo vệ bằng randomized CSFLE vì workflow không yêu cầu tìm kiếm theo nội dung ghi chú.

### 6.2. Các query sai ý định

~~~javascript
// Không hỗ trợ equality plaintext trên randomized encrypted field:
await encryptedCollection.findOne({
  medicalNote: "dị ứng penicillin"
});
~~~

~~~javascript
// Regex cũng không mang ý nghĩa trên ciphertext:
await encryptedCollection.find({
  medicalNote: /penicillin/i
}).toArray();
~~~

Nếu một yêu cầu mới đòi tìm ghi chú theo từ khóa, không thể chỉ thêm index để khôi phục khả năng search. Cần xem lại **threat model, loại mã hóa, khả năng QE và kiến trúc dữ liệu/metadata phụ trợ**.

### 6.3. Không dùng unique index để bảo đảm giá trị gốc duy nhất

Nếu hai document đều có:

~~~text
medicalNote plaintext = "same value"
~~~

randomized encryption tạo ciphertext khác nhau. Một unique index đặt trên ciphertext có thể coi đó là **hai giá trị khác nhau** và cho phép cả hai document tồn tại.

Vì vậy, uniqueness của plaintext cần được thiết kế bằng một cơ chế khác, không chỉ dựa trên unique index của randomized ciphertext.

### 6.4. Không cần encrypt mọi field

Một thiết kế có thể giữ **identity.primaryKey** ở dạng khóa ngẫu nhiên không mang thông tin nhạy cảm để tìm document, rồi mã hóa randomized những field ít phải truy vấn.

Chìa khóa là đảm bảo **khóa tìm kiếm đó thật sự không tiết lộ thông tin bị cấm**, có uniqueness và access-control phù hợp. Tránh lấy số định danh bí mật rồi chỉ đổi tên field thành publicLookupKey.

## 7. Queryable Encryption: queryType quyết định giới hạn

Với QE, cấu hình field trong **encryptedFields** cho biết field được mã hóa và loại truy vấn được phép thực hiện.

### 7.1. Mã hóa nhưng không tìm trên field: queryType none

Ví dụ về **fragment** của encryptedFields schema:

~~~javascript
{
  path: "medicalNotes",
  bsonType: "string"
  // Không khai báo queries -> mặc định không queryable.
}
~~~

Field được mã hóa nhưng không có encrypted-query index để tìm trực tiếp theo plaintext. Ứng dụng tìm theo các metadata khác rồi driver giải mã nội dung khi đọc.

### 7.2. Equality queryType

~~~javascript
{
  path: "identity.taxId",
  bsonType: "string",
  queries: {
    queryType: "equality"
  }
}
~~~

Field được thiết kế cho **exact matching**. Với driver/QE setup hợp lệ:

~~~javascript
await encryptedCollection.findOne({
  "identity.taxId": "TAX-000123"
});
~~~

Server xử lý qua cơ chế QE mà không cần biết taxId plaintext. Điều này không biến field thành full-text search hoặc làm các toán tử string khác mặc định được hỗ trợ.

### 7.3. Range queryType

Với bản MongoDB hỗ trợ range QE (tính năng GA từ MongoDB 8.0), có thể khai báo một field số hoặc Date:

~~~javascript
{
  path: "salary",
  bsonType: "int",
  queries: {
    queryType: "range",
    min: 0,
    max: 1000000
  }
}
~~~

Ví dụ tìm:

~~~javascript
await encryptedCollection.find({
  salary: {
    $gte: 50000,
    $lt: 100000
  }
}).toArray();
~~~

Giá trị **min**, **max** và những tham số như **sparsity, trimFactor, precision** ảnh hưởng chi phí lưu metadata, hiệu năng và phạm vi giá trị được tìm; cách cấu hình chính xác phải theo version và bsonType. Đây là fragment minh họa, chưa phải quy trình tạo collection và KMS hoàn chỉnh.

### 7.4. String queryType: prefix, suffix, substring

Trong các bản hỗ trợ **QE string queries**, có thể bật:

- **prefix**: giá trị bắt đầu bằng một tiền tố.
- **suffix**: giá trị kết thúc bằng một hậu tố.
- **substring**: giá trị chứa một chuỗi con.

Ví dụ nghiệp vụ:

~~~text
prefix("INV-2026-")
suffix("-00418")
substring("PAY")
~~~

Các truy vấn này không giống dùng regex tùy ý trên ciphertext. Chúng sử dụng **query type và biểu thức dành riêng** của QE, với các giới hạn:

- Chỉ áp dụng cho **BSON String** theo tính năng.
- Có tham số về **caseSensitive**, **diacriticSensitive** và độ dài chuỗi truy vấn.
- **Prefix và suffix** có thể được cấu hình cùng nhau trên một field ở phiên bản hỗ trợ.
- **Substring** không được kết hợp tự do với mọi queryType khác trên cùng field.
- Giới hạn độ dài, thuật toán **string** và compatibility khác nhau giữa bản **8.2 preview** và **9.0 GA**.

**Lịch sử phiên bản:** MongoDB 8.2 có public preview của string queries với query types/algorithm tương ứng phiên bản đó; MongoDB 9.0 đưa loại prefix/suffix/substring mới vào GA. Không sao chép nguyên cấu hình preview 8.2 sang 9.0 mà không đọc hướng dẫn migration; các tên **prefixPreview/suffixPreview/substringPreview** dùng thuật toán **text** của preview đã bị deprecate/remove ở 9.0 theo thông báo tài liệu.

### 7.5. Không được chọn nhiều queryType tùy tiện

Không nên cho rằng một field có thể bật mọi query:

~~~text
salary:
  equality + range + prefix + substring
~~~

Trong QE, **query type là cấu hình có ràng buộc**. Các trường số/Date thường chọn equality hoặc range; một field cấu hình range có thể hỗ trợ equality theo cách engine thực hiện, nhưng không có nghĩa schema được khai báo đồng thời hai type tùy ý.

Với String queries, prefix/suffix có quy tắc tổ hợp riêng và substring có ràng buộc riêng. Những thay đổi cấu hình queryable field thường cần **migration/rebuild collection/index**, không chỉ sửa một JSON object trên MongoClient đang chạy.

### 7.6. Cái gì được hỗ trợ không đồng nghĩa có hiệu năng như plaintext

Một range query đã được hỗ trợ vẫn phải xử lý encrypted query metadata; nó có thể có:

- Nhiều metadata entries hơn equality.
- Overhead cho insert/update và cleanup.
- Latency phụ thuộc độ chọn lọc và cấu hình range.
- Dung lượng phụ thuộc sparsity/trimFactor/precision.

Việc string substring được hỗ trợ không có nghĩa nó sẽ có cùng profile hiệu năng/chi phí với một ordinary text index trên dữ liệu không mã hóa.

## 8. Ma trận truy vấn trên encrypted fields

Bảng dưới đây tóm tắt **khả năng theo ý nghĩa plaintext**; luôn kiểm tra giới hạn chính xác của version/driver, query type và BSON type.

| Phép truy vấn | CSFLE deterministic | CSFLE randomized | QE equality | QE range | QE string query |
|---|---|---|---|---|---|
| Truy vấn theo _id/tenantId không mã hóa | Có | Có | Có | Có | Có |
| Đọc field và giải mã với khóa | Có | Có | Có | Có | Có |
| $exists trên encrypted field | Có theo rule | Có theo rule | Có theo rule | Có theo rule | Tùy rule |
| $eq literal plaintext | Có với điều kiện | Không | Có | Có qua range semantics | Tùy operator string |
| $in / $nin literal | Có với điều kiện | Không | Có | Có qua phạm vi hỗ trợ | Tùy support |
| $gt / $gte / $lt / $lte | Không trên plaintext | Không | Không | Có | Không như range numeric |
| Regex tùy ý | Không | Không | Không | Không | Không; dùng QE string ops riêng |
| Prefix/suffix/substring | Không | Không | Không | Không | Có khi bật queryType và phiên bản phù hợp |
| $sort theo plaintext encrypted | Không | Không | Không | Không tự được phép | Không tự được phép |
| $sum/$avg trên encrypted numbers | Không | Không | Không | Không tự được phép | Không áp dụng |
| Exact unique bằng unique(ciphertext) | Cần đánh giá giới hạn và rò rỉ | Không bảo đảm plaintext | Không bảo đảm | Không bảo đảm | Không bảo đảm |
| Full text/Atlas Search trên plaintext encrypted | Không trực tiếp | Không trực tiếp | Không trực tiếp | Không trực tiếp | Chỉ tính năng string query được định nghĩa, không phải general search |

**Cách đọc:** “Có” trong bảng không có nghĩa mọi biến thể cú pháp đều hợp lệ; ví dụ so sánh với **null**, **array** hoặc một field encrypted khác có thể bị chặn dù operator được liệt kê. “Không” nghĩa không dùng phép đó **như query plaintext đúng ngữ nghĩa tại server**; không cấm ứng dụng được ủy quyền đọc/decrypt rồi xử lý một tập nhỏ ở phía client nếu security và hiệu năng cho phép.

## 9. Index thông thường thay đổi ý nghĩa khi field được mã hóa

Với document không mã hóa:

~~~javascript
db.customers.createIndex({ email: 1 });
~~~

B-tree index giúp MongoDB tìm theo **giá trị email plaintext**. Với field đã mã hóa, server chỉ nhận ciphertext. Index tạo trên ciphertext (nếu được phép) tổ chức **byte/ciphertext**, không tự sinh khả năng truy vấn theo mọi ngữ nghĩa của email plaintext.

### 9.1. CSFLE deterministic và index equality

Với deterministic encryption ổn định cùng khóa/scheme, index thông thường trên field ciphertext có thể hỗ trợ **exact equality query** theo điều kiện server/driver phù hợp:

~~~javascript
// Chỉ cân nhắc khi field dùng deterministic CSFLE.
db.customers.createIndex({
  "identity.taxId": 1
});
~~~

Nếu query đi qua driver automatic CSFLE phù hợp:

~~~javascript
await encryptedCollection.findOne({
  "identity.taxId": "TAX-000123"
});
~~~

thì server có thể tìm ciphertext được driver tạo. Nhưng:

- Không làm **range** trở thành đúng.
- Không làm **regex/collation** trở thành đúng.
- Không che giấu việc nhiều document có cùng ciphertext.
- Không tự bảo đảm query theo một khóa mã hóa khác vẫn match.
- Cần xem quy tắc tương thích index/field loại cụ thể của MongoDB.

Không khuyến nghị index deterministic trên một field có rất ít giá trị nếu threat model không chấp nhận frequency leakage.

### 9.2. CSFLE randomized và index

Vì ciphertext của cùng plaintext có thể khác nhau:

~~~text
email plaintext: user@example.com
   -> Ciphertext 1
   -> Ciphertext 2
   -> Ciphertext 3
~~~

một B-tree index thông thường trên field chứa randomized ciphertext **không thể thực hiện equality lookup theo plaintext**.

Ngay cả khi lệnh createIndex thành công, “có index” không có nghĩa có cách sinh ra chính xác ciphertext cần so sánh cho mọi document.

### 9.3. QE: không tạo B-tree index trên encrypted field để tăng tốc

Tài liệu MongoDB cảnh báo **không tạo index trên chính QE encrypted field** để phục vụ query; điều đó có thể làm giảm hiệu năng, trong khi Queryable Encryption dùng cơ chế metadata/query index chuyên biệt.

Không nên:

~~~javascript
// Không phải chiến lược index được khuyến nghị cho QE field.
db.secureRecords.createIndex({
  "identity.taxId": 1
});
~~~

Thay vào đó, ở mô hình được MongoDB hỗ trợ:

- Tạo QE collection với **encryptedFields schema** thích hợp.
- Cho server/driver quản lý encrypted query metadata theo quy trình.
- Khi được tài liệu khuyến nghị, có thể dùng một index trên **__safeContent__** để phục vụ cơ chế query, chứ không tự tạo một index B-tree trên plaintext giả định.

Ví dụ dạng index được tài liệu đề cập:

~~~javascript
// Chỉ làm theo hướng dẫn dành cho QE và phiên bản thực tế.
db.secureRecords.createIndex({
  __safeContent__: 1
});
~~~

**__safeContent__** là thành phần kỹ thuật của Queryable Encryption, không phải field business để ứng dụng đọc/ghi/chỉnh sửa tùy tiện. Không coi index này là một cách thay thế khai báo **queries/queryType**.

### 9.4. Index metadata không mã hóa

Một mô hình có thể tạo:

~~~javascript
db.secureRecords.createIndex({
  tenantId: 1,
  createdAt: -1
});
~~~

nếu tenantId/createdAt được phép ở dạng không mã hóa. Index này hỗ trợ truy vấn:

~~~javascript
db.secureRecords.find({
  tenantId: "TENANT-A",
  createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
}).sort({ createdAt: -1 });
~~~

Đó là index/truy vấn **trên metadata plaintext**, không phải trên field lương, taxId hay ghi chú bí mật. Một truy vấn QE còn phải đáp ứng giới hạn câu lệnh của driver/phiên bản.

### 9.5. Index theo token tìm kiếm phụ trợ

Một số hệ thống thêm một **search token** tách biệt để tra cứu, ví dụ:

~~~javascript
{
  tenantId: "TENANT-A",
  opaqueLookupToken: BinData(/* token theo thiết kế */),
  secretValue: BinData(/* encrypted field */)
}
~~~

Nếu sử dụng cách này, token cần được thiết kế bằng cryptography có key (chẳng hạn **HMAC**) hoặc phương án an toàn được đánh giá; **không được chỉ dùng SHA-256 của giá trị dễ đoán rồi coi đó là giải pháp bảo mật**.

Các rủi ro:

- Frequency leakage.
- Dictionary/brute-force trên miền giá trị nhỏ.
- Token collision hoặc normalization mismatch.
- Key lifecycle, rotation và scope giữa tenant.
- Khả năng suy luận qua metadata/index/query patterns.

Một shadow/blind index là **một thiết kế mật mã bổ sung**, không phải phương án thay thế đơn giản, luôn tốt hơn QE.

## 10. Unique indexes: không thể suy ra uniqueness của plaintext

Với một field plaintext:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
);
~~~

MongoDB có thể kiểm tra uniqueness theo giá trị field/index key được lưu.

Nhưng nếu email là **randomized encrypted** hoặc **Queryable Encryption**:

~~~text
user@example.com -> Ciphertext A
user@example.com -> Ciphertext B
~~~

server có thể coi A và B là hai giá trị khác nhau. Unique index trên ciphertext **không bảo đảm business rule “một email chỉ thuộc một tài khoản”**.

### 10.1. QE luôn cần đánh giá unique ở tầng nghiệp vụ

Tài liệu MongoDB nêu rõ unique index có encrypted field trong QE **không bảo đảm uniqueness của plaintext**. Không tạo:

~~~javascript
// Không dùng làm bảo đảm uniqueness của email plaintext trong QE.
db.customers.createIndex(
  { tenantId: 1, encryptedEmail: 1 },
  { unique: true }
);
~~~

rồi xem đây là ràng buộc business đã được thực thi chắc chắn.

### 10.2. CSFLE deterministic có thể so sánh ciphertext nhưng không phải lời giải mọi trường hợp

Deterministic encryption với **cùng khóa, cùng kiểu, cùng normalization và cùng thuật toán** tạo ciphertext lặp lại cho cùng plaintext. Điều này có thể giúp ràng buộc equality/uniqueness trên ciphertext trong một thiết kế hẹp.

Nhưng phải xét:

- Có nhiều key/version mã hóa không?
- Có thay đổi normalization hoặc kiểu BSON không?
- Có client ghi ngoài schema encryption không?
- Có sharding và quy tắc unique index cross-shard không?
- Có rủi ro frequency leakage không?
- Có yêu cầu unique theo giá trị sau chuẩn hóa ở toàn tenant không?

Không tuyên bố một unique index deterministic ciphertext **luôn** bảo đảm ràng buộc danh tính bất kể topology/migration.

### 10.3. Tách uniqueness key và confidential field

Một hướng thiết kế là dùng **mã định danh nghiệp vụ không tiết lộ bí mật**:

~~~javascript
{
  _id: "CUSTOMER-1001",
  tenantId: "TENANT-A",
  externalCustomerRef: "CREF-1001",
  encryptedEmail: BinData(/* QE */)
}
~~~

Unique index có thể áp dụng cho externalCustomerRef theo scope mong muốn, nếu business rule là “customer reference duy nhất”.

Nhưng nếu cần business rule chính là **email plaintext duy nhất**, externalCustomerRef **không thay thế** điều kiện đó. Cần một thiết kế registry/dedup có tính nguyên tử và phân quyền phù hợp hoặc một cryptographic lookup key đã được review, không dựa vào cách “query trước rồi insert sau” không có bảo vệ concurrency.

### 10.4. Check-before-insert có thể bị race

Kịch bản:

~~~text
Request A: find(email) -> chưa có
Request B: find(email) -> chưa có
Request A: insert(email)
Request B: insert(email)
~~~

Nếu không có một primitive atomic uniqueness phù hợp, cả A và B có thể insert thành công.

Mã hóa không tự loại bỏ race condition; **tính duy nhất** và **tính bảo mật** phải được giải quyết đồng thời bằng mô hình phù hợp.

## 11. Sharding và encrypted fields

Shard key giúp mongos định tuyến write/read dựa trên những giá trị của shard key. Nếu một field bị mã hóa, giá trị ciphertext không thể mặc định duy trì những tính chất mà shard key/query router cần.

### 11.1. Không dùng QE encrypted field làm shard key

Trong Queryable Encryption, shard key **không được là encrypted field**. Các collection metadata nội bộ QE cũng có ràng buộc không được shard theo mô hình tự do.

Ví dụ không phù hợp:

~~~javascript
// Không dùng taxId được QE encrypt làm shard key.
sh.shardCollection(
  "secure_db.customers",
  { "identity.taxId": 1 }
);
~~~

Thay vào đó, chọn một shard key dựa trên field được phép lộ theo chính sách, đủ cardinality và phù hợp query patterns, ví dụ một tenantId hoặc opaque tenant routing key.

### 11.2. CSFLE encrypted shard key cũng có nguy cơ sai

Với CSFLE, MongoDB cảnh báo việc dùng encrypted field trong shard key hoặc mã hóa field shard key đang có có thể gây **sharding behavior sai hoặc khó dự đoán**. Không mặc định deterministic ciphertext giải quyết toàn bộ điều kiện shard routing.

Kiến trúc nên giữ shard key **không bị mã hóa**, được lựa chọn có chủ đích và không làm lộ dữ liệu bị cấm.

### 11.3. Một thiết kế minh họa

~~~javascript
{
  tenantId: "TENANT-A",            // Routing metadata được phép
  recordId: "REC-1001",           // ID không nhạy cảm
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  identity: {
    taxId: BinData(/* QE encrypted */)
  },
  salary: BinData(/* QE encrypted */)
}
~~~

Shard key có thể xét:

~~~javascript
{ tenantId: 1, recordId: 1 }
~~~

Nhưng cần đánh giá cardinality, hotspot, query targeting, unique indexes và quyền riêng tư. Không tự biến một số định danh bí mật thành shard key plaintext chỉ để đạt throughput.

### 11.4. QE topology và transaction

Các bản Queryable Encryption hỗ trợ **replica sets và sharded clusters** theo điều kiện triển khai; **standalone** thường không được hỗ trợ cho QE đầy đủ. Secondary reads và giao dịch trên sharded clusters có những ràng buộc riêng. Theo tài liệu version cũ, transaction với sharded QE cần **readConcern: "snapshot"**.

Luôn đọc compatibility matrix của phiên bản triển khai: không mặc định “MongoDB hỗ trợ transactions” đồng nghĩa mọi tổ hợp **QE + sharding + read preference + transaction** đều hoạt động như collection plaintext.

## 12. Sorting trên field mã hóa

Ví dụ một danh sách nhân viên:

~~~javascript
db.employees.find({
  tenantId: "TENANT-A"
}).sort({
  salary: -1
});
~~~

Nếu salary được QE range encrypt, bạn có thể **lọc trong khoảng** theo queryType được hỗ trợ. Nhưng điều đó **không có nghĩa** MongoDB được phép hoặc có thể sắp xếp kết quả theo salary plaintext.

Khả năng tìm “salary thuộc [50000,100000)” và khả năng trả “salary giảm dần” là **hai bài toán khác nhau**.

### 12.1. Sort dựa trên ciphertext không phải sort plaintext

Không dùng thứ tự byte của encrypted BinData như thứ tự tiền lương, điểm số hoặc ngày.

~~~text
Salary plaintext:  30000, 50000, 90000
Ciphertext order:  không có quan hệ thứ tự đáng tin với số gốc
~~~

### 12.2. Sort theo metadata không mã hóa

Nếu chính sách cho phép, có thể:

~~~javascript
db.employees.find({
  tenantId: "TENANT-A"
}).sort({
  createdAt: -1
}).limit(20);
~~~

Trong QE, sort trên field không mã hóa có thể xuất hiện trong danh sách supported aggregation stages/ordinary query operations, nhưng yêu cầu **chính xác của driver và pipeline** vẫn phải được đối chiếu. Không suy ra vì có sort stage được hỗ trợ mà có thể sort một encrypted salary.

### 12.3. Sort sau khi giải mã ở client

Một lựa chọn khác:

1. Lọc ứng viên theo tenant/trạng thái/quyền.
2. Đọc một tập dữ liệu **có kích thước giới hạn**.
3. Giải mã các giá trị ở client được ủy quyền.
4. Sort locally theo salary.

Rủi ro:

- Cần đọc nhiều dữ liệu hơn.
- Chỉ sort được **đúng toàn cục** nếu đã lấy đủ tập ứng viên; sort một trang rồi trả top-10 có thể sai kết quả toàn corpus.
- Lộ plaintext trong memory/log của ứng dụng nếu quản lý kém.
- Không scale tốt với hàng triệu document.

Đừng dùng client-side sort như một cách “khôi phục mọi chức năng của MongoDB” mà bỏ qua SLA và bảo mật.

## 13. Aggregation và phép toán trên encrypted fields

Một field không mã hóa là kiểu Number/String/Date phù hợp với những aggregation operator thông thường. Khi encrypt phía client, MongoDB nhìn thấy ciphertext và **không tự giải mã để tính toán**.

### 13.1. Không tính tổng, trung bình tiền lương trên ciphertext

~~~javascript
// Không phải phép tính salary plaintext hợp lệ trong CSFLE/QE:
db.employees.aggregate([
  {
    $group: {
      _id: "$departmentId",
      avgSalary: { $avg: "$salary" },
      totalSalary: { $sum: "$salary" }
    }
  }
]);
~~~

Nếu salary mã hóa, server không có giá trị Number plaintext để tính $avg/$sum. Một số pipeline/driver sẽ báo lỗi; ở dạng explicit encryption, xử lý BinData có thể cho kết quả không mong đợi. **Không coi thiếu lỗi là bằng chứng tính toán đúng.**

Các hướng thay thế:

- Tính ở **client được ủy quyền** trên một tập giới hạn sau khi giải mã.
- Tạo bảng **aggregate không nhạy cảm hoặc đã được cho phép tiết lộ** theo policy.
- Dùng công cụ tính toán/mã hóa chuyên dụng được review nếu yêu cầu thật sự cần phép toán bảo mật trên dữ liệu lớn.

Không tự thêm một field plaintext salaryTotal vào cùng document nếu chính sách cấm tiết lộ thông tin đó.

### 13.2. $group theo field mã hóa

CSFLE deterministic có thể hỗ trợ một số trường hợp **$group theo deterministically encrypted field**, với giới hạn expression/stage và khả năng rò rỉ pattern trùng giá trị. Điều này **không có nghĩa** mọi accumulator làm việc trên plaintext.

Ví dụ cần phân biệt:

~~~text
Group salary deterministically encrypted:
  Có thể nhóm các ciphertext bằng nhau theo cấu hình được hỗ trợ.

Average salary deterministically encrypted:
  Không thể lấy trung bình plaintext chỉ từ BinData.
~~~

Với QE, tài liệu về automatic encryption liệt kê **$group trên field không mã hóa** là một trường hợp được hỗ trợ, chứ không cho phép group tùy ý trên encrypted fields.

### 13.3. $project có thể hiển thị nhưng không làm tính toán tùy ý

Một pipeline chỉ lấy các trường và để driver giải mã phần encrypted payload có thể được hỗ trợ:

~~~javascript
db.employees.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  {
    $project: {
      employeeCode: 1,
      departmentId: 1,
      salary: 1
    }
  }
]);
~~~

Nhưng phép:

~~~javascript
{
  $project: {
    salaryAfterRaise: { $multiply: ["$salary", 1.05] }
  }
}
~~~

không thể coi là phép tính trên số lương plaintext khi server chỉ thấy ciphertext.

### 13.4. Các stage được hỗ trợ không đồng nghĩa mọi biểu thức được hỗ trợ

Tài liệu MongoDB cho QE automatic encryption có danh sách stage được hỗ trợ như:

- **$match**, **$project**, **$addFields** trong những phạm vi phù hợp.
- **$sort**, **$limit**, **$skip** với các field và cú pháp được phép.
- **$group** trên unencrypted fields.
- **$lookup/$graphLookup** với giới hạn riêng.

Nhưng trong mỗi stage, các biểu thức trực tiếp thao tác trên encrypted field vẫn phải ở **danh sách cho phép**.

Một pipeline có $project hợp lệ về stage vẫn có thể lỗi vì dùng **$toLower** hoặc **$concat** trên encrypted String. Không suy ra mọi phép biến đổi trong aggregation đều được phép.

### 13.5. $lookup và join key

Ví dụ thông thường:

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerRef",
      foreignField: "customerRef",
      as: "customer"
    }
  }
]);
~~~

Nếu **customerRef** là field mã hóa, đừng mặc định join sẽ so sánh plaintext đúng nghĩa. Trong những phiên bản hỗ trợ QE automatic encryption, tài liệu hạn chế dùng **encrypted field làm localField/foreignField**, và có các quy tắc riêng cho nhiều encrypted collections, encrypted arrays và subpipelines.

**Phương án đơn giản hơn:** dùng một **opaque customerRef không nhạy cảm** để join, còn những thông tin nhạy cảm như nationalId, email hoặc salary được mã hóa riêng.

### 13.6. $out và $merge

Queryable Encryption automatic encryption không hỗ trợ tự do những aggregation stage **ghi sang collection khác**, ví dụ **$out** và **$merge**. Không nên lập một pipeline từ encrypted collection rồi cho rằng một phép $merge sẽ tái mã hóa đúng từng field ở collection đích.

Khi cần ETL hoặc chuyển dữ liệu:

1. Xác định ranh giới quyền giải mã.
2. Chọn collection đích và encryption schema tương ứng.
3. Dùng client/migration có cấu hình mã hóa đúng để ghi.
4. Kiểm tra không có cửa sổ dữ liệu plaintext bị lưu ngoài policy.

### 13.7. $text, regex, MongoDB Search và Vector Search

Không nên dùng:

~~~javascript
// Không tìm trên plaintext encrypted String:
db.customers.find({
  $text: { $search: "Nguyen" }
});
~~~

QE **không tương thích MongoDB Atlas Search** trên encrypted fields theo các giới hạn được công bố; CSFLE cũng không tự tạo khả năng full-text/index n-gram trên ciphertext.

Trong môi trường client automatic encryption, **$text** còn có thể bị driver từ chối dù mục tiêu là một field khác, tùy tập supported operators.

**Vector Search** cũng không được phép hiểu là một cách tìm ngữ nghĩa trực tiếp bên trong field client-side encrypted. Vector embedding và search index là một pipeline khác; nếu tạo embedding từ plaintext và lưu dưới dạng có thể search, embedding có thể tiết lộ thông tin và phải được đánh giá như một sản phẩm dẫn xuất nhạy cảm.

### 13.8. Lý do phải kiểm tra đúng collection và client

Một aggregation trên collection plaintext có thể chạy, trong khi **cùng pipeline qua MongoClient đã bật automatic encryption** bị giới hạn hoặc từ chối do encryption support library kiểm soát supported stages/commands.

Không áp dụng kết quả từ một client debug không mã hóa để khẳng định service production QE sẽ chạy giống hệt.

## 14. Update, replace và upsert với encrypted fields

Mã hóa trường ảnh hưởng không chỉ SELECT/find mà cả cách cập nhật.

### 14.1. $set và $unset

Queryable Encryption automatic encryption hỗ trợ những update operator như:

- **$set**
- **$unset**

trên encrypted fields trong các điều kiện hợp lệ. Ví dụ logic:

~~~javascript
// Client đã cấu hình QE, field salary được định nghĩa là encrypted.
await encryptedCollection.updateOne(
  {
    tenantId: "TENANT-A",
    recordId: "REC-1001"
  },
  {
    $set: {
      salary: 85000
    }
  }
);
~~~

Driver phải mã hóa salary mới đúng schema; server không nhận số plaintext cho field đó trong luồng QE.

### 14.2. Không dùng $inc trên lương được mã hóa

~~~javascript
// Không được hiểu là cộng trên plaintext encrypted salary:
await encryptedCollection.updateOne(
  { recordId: "REC-1001" },
  { $inc: { salary: 5000 } }
);
~~~

**$inc** yêu cầu server đọc giá trị số hiện tại và cộng thêm. Với ciphertext BinData, server không có số plaintext để tính. Cách thay thế:

1. Đọc document qua client có quyền giải mã.
2. Kiểm tra authorization và business constraints.
3. Tính salary mới tại ứng dụng.
4. Ghi bằng **$set** qua encrypted client.
5. Có cơ chế **concurrency control** để tránh lost update.

Không làm read-modify-write không có phiên bản trong hệ thống đồng thời cao.

### 14.3. Ví dụ optimistic concurrency

~~~javascript
// Ví dụ giả định record được đọc và giải mã trước đó.
const originalVersion = 7;
const updatedSalary = 85000;

const result = await encryptedCollection.updateOne(
  {
    tenantId: "TENANT-A",
    recordId: "REC-1001",
    version: originalVersion
  },
  {
    $set: {
      salary: updatedSalary,
      version: originalVersion + 1
    }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Version conflict: reload and retry");
}
~~~

Trong thiết kế này, **version là metadata không mã hóa** do threat model cho phép. Server kiểm tra điều kiện version atomically khi updateOne. Ứng dụng phải xử lý retry mà không áp dụng raise hai lần; không tự coi mẫu trên là toàn bộ giao dịch payroll.

### 14.4. Không updateMany tùy ý trong QE

Queryable Encryption có những giới hạn đối với **multi-document update/delete**. Tài liệu MongoDB nêu các thao tác như **updateMany** và những bulk writes chứa nhiều update/delete statements không được hỗ trợ trong các điều kiện QE được mô tả.

Không nên:

~~~javascript
// Không dùng như một migration QE production:
await encryptedCollection.updateMany(
  { tenantId: "TENANT-A" },
  { $set: { salary: 90000 } }
);
~~~

Thay vào đó, cần một **migration worker có kiểm soát**: duyệt tài liệu qua client hỗ trợ, thao tác từng document theo điều kiện hợp lệ, checkpoint, retry/idempotency và quan sát write amplification.

### 14.5. Upsert có encrypted filter

Một điểm dễ mắc lỗi: với QE, khi upsert, những field mã hóa nằm trong **query filter** có thể **không tự động được sao chép vào document mới** như một số người mong đợi.

Ví dụ:

~~~javascript
// Rủi ro giả định encrypted field tự được đưa vào inserted doc.
await encryptedCollection.updateOne(
  {
    "identity.taxId": "TAX-000123"
  },
  {
    $set: { status: "ACTIVE" }
  },
  { upsert: true }
);
~~~

Không suy ra document vừa tạo sẽ chắc chắn có **identity.taxId** đúng schema. Cần chủ động thiết kế giá trị cần insert và kiểm thử upsert behavior theo version, đồng thời không dùng upsert như một cơ chế uniqueness khi schema/index không bảo đảm điều đó.

### 14.6. Replacement update

Replacement-style update có thể được hỗ trợ trong điều kiện cụ thể. Nhưng:

- Driver phải có encryption config tương thích.
- Replacement phải chứa các field bắt buộc theo schema.
- Không để thiếu tenantId/shard key hoặc fields cần giữ.
- Không vô tình ghi plaintext qua một client không cấu hình encryption.

Một lệnh replaceOne có thể thay toàn bộ document business fields, nên trong hệ thống có dữ liệu bí mật cần đặc biệt thận trọng với việc mất field hoặc sai encryption metadata.

### 14.7. Thao tác $rename

Trong CSFLE, một số trường hợp **$rename** có thể được hỗ trợ nếu source/target có encryption metadata tương ứng. Với QE, encrypted field names được ràng buộc bởi schema và không được đổi tên tự do.

Không tạo một script:

~~~javascript
// Không dùng tùy tiện trên QE encrypted field:
db.secureRecords.updateOne(
  { recordId: "REC-1001" },
  { $rename: { "identity.taxId": "taxReference" } }
);
~~~

và mong encrypted query config tự dịch sang tên mới. Di chuyển field mã hóa thường là **schema migration có decrypt/re-encrypt**.

## 15. Null, missing fields và các BSON type có giới hạn

Khi một field được mã hóa, không nên giả định xử lý **null** giống như field plaintext.

### 15.1. Null không đồng nghĩa không có field

Với collection thông thường:

~~~javascript
{ name: null }
{ /* không có name */ }
~~~

Lệnh:

~~~javascript
db.people.find({ name: null });
~~~

có hành vi MongoDB riêng liên quan giá trị null và field missing. Nhưng trong automatic CSFLE/QE, các tài liệu về supported operators cho biết **so sánh encrypted field với null** có thể bị từ chối, ngay cả khi operator $eq được hỗ trợ cho các loại giá trị khác.

Không dùng:

~~~javascript
// Không xem đây là phép so sánh encrypted null hợp lệ.
await encryptedCollection.find({
  secretField: { $eq: null }
}).toArray();
~~~

### 15.2. Mô hình optional field

Một cách xử lý:

~~~javascript
{
  tenantId: "TENANT-A",
  recordId: "REC-1001",
  hasMedicalNote: true,     // metadata được phép lộ nếu policy cho phép
  medicalNote: BinData(/* encrypted */)
}
~~~

Với bản ghi không có medicalNote:

~~~javascript
{
  tenantId: "TENANT-A",
  recordId: "REC-1002",
  hasMedicalNote: false
}
~~~

Ứng dụng dùng **$exists** hoặc một boolean metadata hợp lệ để tìm những record có/không có ghi chú, chứ không ép phải mã hóa null.

**Trade-off:** hasMedicalNote cho thấy record có ghi chú. Đây có thể là thông tin nhạy cảm, nên phải xem liệu có được phép tiết lộ sự tồn tại của field hay không.

### 15.3. BSON types của QE theo queryType

Tài liệu MongoDB về QE quy định kiểu BSON hợp lệ cho từng queryType. Ví dụ:

| Query type | Kiểu dữ liệu điển hình |
|---|---|
| equality | Nhiều BSON scalar types, trừ những loại bị hạn chế như array, object, double/decimal với equality index |
| range | **date, int, long, double, decimal** theo phiên bản |
| prefix/suffix/substring | **string** theo tính năng tương ứng |
| none | Có thể hỗ trợ thêm kiểu như array/object, nhưng không query nội dung trực tiếp |

Một field **double/decimal** cần so sánh equality có thể phải dùng **range index** theo tài liệu QE, không thể mặc định bật equality queryType như với String.

Không tự đổi **bsonType: "int"** thành **"long"** hoặc **"double"** giữa hai client nếu schema/index đang chờ một kiểu cụ thể.

### 15.4. Những giá trị BSON không được mã hóa tự do

Các giá trị như **MinKey, MaxKey, null, undefined** có những hạn chế vì mã hóa không che giấu đầy đủ type information; nhiều trường hợp QE không hỗ trợ encrypt chúng.

Không lưu:

~~~javascript
{
  salary: undefined,
  encryptedString: null
}
~~~

rồi kỳ vọng client automatic encryption có thể mã hóa đúng mọi giá trị.

Với field bắt buộc, hãy validate **trước khi gửi qua encrypted client**; với field optional, xác định rõ chính sách **missing**.

### 15.5. Integer hay floating-point

Một field như:

~~~javascript
salary: 50000
~~~

có thể được serialize thành các BSON number types khác nhau tùy driver/cách xây document. Nếu QE schema định nghĩa **bsonType: "int"**, đừng để code path khác ghi **double** cho cùng field.

Trong Java, phân biệt **Integer, Long, Double, Decimal128**; trong JavaScript/Python cần chú ý serializer, **Int32/Long** wrapper khi cần. Chọn kiểu dữ liệu theo miền giá trị và bảo đảm nhất quán ở ingestion/query.

### 15.6. $in và mảng giá trị

Hai trường hợp khác nhau:

~~~javascript
// Query scalar encrypted field với danh sách scalar values.
{ "identity.taxId": { $in: ["TAX-1", "TAX-2"] } }
~~~

và:

~~~javascript
// Field được mã hóa chứa chính một array.
{ tags: ["A", "B"] }
~~~

Trường hợp đầu có thể được một số queryType/driver hỗ trợ. Trường hợp sau có ràng buộc riêng: **encrypted array** không tự hỗ trợ $elemMatch, $all hoặc query trên từng phần tử như một array plaintext.

## 16. Arrays, objects và nested fields

### 16.1. CSFLE deterministic không mã hóa tùy ý cả object/array

Ví dụ:

~~~javascript
{
  address: {
    line1: "A Street",
    city: "HCM",
    postalCode: "700000"
  },
  phones: ["+84-...", "+84-..."]
}
~~~

Deterministic CSFLE có những hạn chế đối với việc mã hóa **nguyên object hoặc array**; tài liệu CSFLE ghi nhận mã hóa cả object/array chỉ được hỗ trợ với randomized encryption trong mô hình đó.

Nếu cần query theo postalCode, một thiết kế có thể mã hóa **postalCode scalar** deterministic hoặc dùng QE theo yêu cầu, nhưng phải xem field path và schema được hỗ trợ. Không thể suy ra sau khi mã hóa randomized toàn object address, MongoDB vẫn truy vấn được address.postalCode.

### 16.2. Nested field trong array of documents

Ví dụ:

~~~javascript
{
  contacts: [
    { type: "HOME", phone: "+84-..." },
    { type: "WORK", phone: "+84-..." }
  ]
}
~~~

CSFLE automatic encryption có hạn chế mã hóa các field nằm **bên trong array of documents**. Queryable Encryption cũng giới hạn việc encrypted field nằm trong array; kiểu mã hóa nguyên array với queryType none **không tự cho phép truy vấn phần tử bên trong**.

Nếu cần tra cứu một số phone theo equality, cân nhắc:

- Tách thành collection **contacts** chứa mỗi contact là một document với trường scalar có thể encrypt/query.
- Dùng một field tra cứu phụ theo threat model.
- Đổi yêu cầu truy vấn nếu phone chỉ cần hiển thị khi đã biết userId.

### 16.3. Không có multikey index “phù phép” cho encrypted array

Index multikey thường hỗ trợ array fields ở MongoDB plaintext. Nhưng với encrypted array, server chỉ thấy payload mã hóa; không có các phần tử plaintext để tạo multikey index có ý nghĩa tìm theo từng phần tử.

Không được coi việc tạo index trên **contacts.phone** là đủ để làm field bên trong một randomized-encrypted contacts array tìm kiếm được.

### 16.4. Thiết kế document theo khả năng query

Hai mô hình:

~~~text
Model A
  userId = plaintext opaque ID
  contacts = randomized encrypted array
  Query: chỉ tìm userId rồi giải mã toàn bộ contacts

Model B
  userId = plaintext opaque ID
  contact documents riêng
  encryptedPhone = QE equality
  Query: tra phone trong contact collection
~~~

Model A phù hợp khi luôn mở contacts sau khi đã biết userId. Model B phù hợp hơn nếu cần tra phone, nhưng tăng số document, encrypted index overhead và chi phí đồng bộ. Không có mô hình thắng trong mọi workload.

## 17. Collation, case-insensitive và normalization

Một field String plaintext có thể dùng collation hoặc regex để so sánh không phân biệt chữ hoa, chữ thường hoặc dấu.

Khi mã hóa:

- **CSFLE deterministic** mã hóa những giá trị byte/canonical form được tạo; không tự áp dụng collation MongoDB trên plaintext.
- **QE** có cơ chế truy vấn String với tham số case/diacritic sensitivity ở phiên bản hỗ trợ, nhưng không đồng nghĩa mọi collation MongoDB được hỗ trợ như plaintext.

### 17.1. Ví dụ email

~~~text
Alice@example.com
alice@example.com
ALICE@EXAMPLE.COM
~~~

Đừng mặc định ba chuỗi là cùng một tài khoản hoặc luôn khác nhau. Quy tắc canonicalization phải được quyết định theo nghiệp vụ/tiêu chuẩn của hệ thống.

Nếu dùng CSFLE deterministic equality và muốn canonical search, ứng dụng cần tạo **cùng canonical form trước khi encrypt cả document lẫn query**.

### 17.2. Không dùng collation như cơ chế tự giải nghĩa ciphertext

~~~javascript
db.customers.find({
  encryptedName: "Nguyen"
}).collation({
  locale: "vi",
  strength: 2
});
~~~

Không thể suy ra server sẽ so sánh encryptedName sau khi giải mã. Tài liệu CSFLE/QE cảnh báo collation có thể không hoạt động như mong đợi trên ciphertext.

### 17.3. Case/diacritic query types của QE

Các chế độ String trong QE mới cho phép khai báo mức nhạy với case/diacritics theo tính năng. Ví dụ khái niệm:

~~~text
queryType: prefix
caseSensitive: false
diacriticSensitive: false
~~~

Đây là **lựa chọn trong encrypted query schema** cần cấu hình từ đầu, không phải sửa tùy ý ở một câu find().

Chi phí và giới hạn String query (độ dài token, text normalization, phiên bản) phải được hiểu đầy đủ trước khi bật.

## 18. Các tính năng không tương thích hoặc phải dùng riêng

Một số tính năng MongoDB không thể kết hợp tùy ý với client-side encrypted fields hoặc QE collection:

| Tính năng | Vấn đề cần lưu ý |
|---|---|
| MongoDB Search/Atlas Search | Không tìm plaintext ẩn trong ciphertext theo full text; QE có hạn chế tương thích |
| Vector Search | Không tự sinh/đọc ngữ nghĩa encrypted field; embedding là dữ liệu dẫn xuất có rủi ro riêng |
| Time series collection | Field-level encryption/QE có hạn chế không tương thích với loại collection này |
| Capped collection | QE có hạn chế đối với capped collection |
| Views | Truy vấn qua view dùng encrypted fields có thể cho kết quả không đúng hoặc bị từ chối |
| Change streams | Có hạn chế về đường theo dõi database/cluster và cách giải mã; không mặc định mọi payload đều plaintext |
| TTL index | QE collection có hạn chế về TTL indexes theo tài liệu phiên bản |
| Unique index | Không bảo đảm uniqueness plaintext cho randomized/QE encrypted fields |
| Sharded collection | Có thể hỗ trợ QE topology nhưng shard key không phải encrypted field |
| $lookup, $graphLookup | Join trên encrypted fields có nhiều giới hạn |
| Transactions | Ràng buộc thêm về topology, read concern, drivers và operations |
| Schema validation | Không tùy ý đưa encrypt keyword hoặc tắt validation với QE; phải theo encryptedFields schema |
| Aggregation $merge/$out | Không được hỗ trợ theo automatic QE như pipeline plaintext tùy ý |

Đây là **bảng định hướng**, không phải kết luận mọi tính năng đều bị cấm tuyệt đối trên mọi phiên bản. Trường hợp dùng field **không mã hóa** trong một QE collection vẫn có thể có hành vi khác với thao tác trên field mã hóa; cần xem đúng compatibility/supported operations.

### 18.1. Time series + CSFLE

MongoDB time series có những hạn chế chung, trong đó tài liệu nêu **không hỗ trợ Client-Side Field Level Encryption** trên time series collections theo mô hình được mô tả.

Nếu sensor readings chứa một số thuộc tính bí mật, hãy cân nhắc:

- Mã hóa dữ liệu nhạy cảm trong **collection thường riêng**.
- Đưa time series metadata ít nhạy cảm vào time series collection khi policy cho phép.
- Sử dụng một registry tách biệt cho ánh xạ từ sensorId opaque sang định danh thật.

Không mặc định có thể thêm CSFLE vào time series collection đã có chỉ bằng một tùy chọn driver.

### 18.2. QE collection: tạo mới, migration và rename

Trong nhiều phiên bản QE, feature yêu cầu **tạo collection với encryptedFields từ đầu**. Không có đường “bật encryption cho collection cũ” tự động mã hóa toàn bộ document và sửa mọi index.

Các hạn chế còn bao gồm:

- Không tùy ý rename encrypted collection.
- Không tự thay đổi queryType của field đã định nghĩa.
- Không chuyển CSFLE encrypted collection sang QE bằng một lệnh collMod.
- Có quy tắc riêng về $jsonSchema, validationAction và validationLevel.
- Metadata collections liên quan phải được tạo/quản lý đúng quy trình.

Vì thế một quyết định encryption schema thường là **quyết định kiến trúc cần migration**, không chỉ một cấu hình nhỏ trên connection string.

### 18.3. QE và các phiên bản trước

Một cluster cũ có thể không hỗ trợ:

- QE range GA.
- QE String prefix/suffix/substring GA.
- Các cấu hình precision/trimFactor/sparsity mới.
- Một số hành vi $lookup với nhiều encrypted collections.

Không xây sản phẩm dựa trên một tính năng xuất hiện trong tài liệu hiện hành nếu server đang chạy version không có tính năng đó.

### 18.4. Automatic vs explicit encryption

**Automatic encryption**:

~~~text
App sends plaintext literal via configured driver
              |
              v
Driver checks encryption schema and supported operations
              |
              v
Encrypt query/write payload and send to server
~~~

**Explicit encryption**:

~~~text
App manually calls encrypt()/decrypt()
              |
              v
App manages encrypted values and query payload
              |
              v
Server sees ciphertext, may operate as BinData
~~~

Explicit encryption không tự giúp một unsupported operator trở thành hợp lệ. Nó còn tăng nguy cơ **query chạy mà ngữ nghĩa sai** nếu ứng dụng quên rằng server so sánh ciphertext, không phải plaintext.

## 19. Thiết kế schema an toàn cho một workload thực tế

Giả sử hệ thống nhân sự cần:

- Tìm nhân viên theo **employeeCode**.
- Lọc theo **tenantId**, **departmentId**, **employmentStatus**, khoảng **createdAt**.
- Tìm chính xác **taxId** khi có quyền.
- Tìm những nhân viên có salary trong khoảng nhất định, nhưng **không cần sắp xếp/tính trung bình salary tại server**.
- Chỉ đọc **medicalNote** sau khi đã tìm nhân viên qua metadata khác.

Một mô hình có thể là:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "TENANT-A",
  employeeCode: "E-1001",
  departmentId: "FINANCE",
  employmentStatus: "ACTIVE",
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  identity: {
    taxId: BinData(/* QE equality */)
  },
  salary: BinData(/* QE range */),
  medicalNote: BinData(/* encrypted, queryType none */)
}
~~~

### 19.1. Bản đồ field và mục đích

| Field | Cách xử lý dự kiến | Query cần hỗ trợ | Ghi chú |
|---|---|---|---|
| _id | Không mã hóa theo QE schema | Exact record lookup | Không dùng _id làm encrypted field QE |
| tenantId | Opaque metadata được phép | Tenant filter | Phải kiểm quyền độc lập |
| employeeCode | Opaque public business ID | Exact + unique theo phạm vi | Không chứa số định danh bí mật |
| departmentId | Plaintext theo threat model | Equality/group | Có thể tiết lộ phòng ban |
| employmentStatus | Plaintext theo threat model | Equality | Có thể tiết lộ tình trạng việc làm |
| createdAt | Plaintext theo threat model | Range/sort | Có thể tiết lộ hoạt động tuyển dụng |
| identity.taxId | QE equality | Exact lookup | Không dùng làm shard key |
| salary | QE range | Numerical range | Không tự cho sort/sum/avg |
| medicalNote | QE none hoặc CSFLE randomized | Không query theo nội dung | Chỉ giải mã sau khi đọc đúng record |

Đây là một **bản thiết kế minh họa**. Với một tổ chức có chính sách cấm lộ departmentId hoặc employmentStatus, cần mã hóa/tách riêng các field đó và chấp nhận giới hạn query tương ứng.

### 19.2. Index cho metadata thông thường

Nếu field được phép ở dạng không mã hóa:

~~~javascript
db.employees.createIndex({
  tenantId: 1,
  employeeCode: 1
});

db.employees.createIndex({
  tenantId: 1,
  departmentId: 1,
  createdAt: -1
});
~~~

Các index này phục vụ **routing/filter/sort trên metadata**, không làm salary được giải mã ở server.

Với Queryable Encryption, index cho encrypted fields được thiết lập qua **encryptedFields schema/metadata mechanism**; không tự thêm index B-tree trên salary/taxId để thực hiện truy vấn plaintext.

### 19.3. Mẫu query theo public ID

~~~javascript
const employee = await encryptedCollection.findOne({
  tenantId: authenticatedTenantId,
  employeeCode: "E-1001"
});
~~~

Khi query đi qua client có quyền và cấu hình encryption, **salary/taxId/medicalNote** trong result có thể được giải mã cho ứng dụng.

Nhưng chỉ vì driver giải mã được **không có nghĩa user cuối có quyền xem cả ba field**. Application layer phải áp dụng authorization và **projection/response DTO** đúng vai trò.

### 19.4. Query taxId equality

~~~javascript
const employee = await encryptedCollection.findOne({
  tenantId: authenticatedTenantId,
  "identity.taxId": "TAX-000123"
});
~~~

Điều kiện:

- taxId đã cấu hình **QE equality**.
- Client dùng đúng encryptedFields schema, keys và support library.
- Giá trị query có BSON type đúng (String).
- tenantId được xác minh từ authentication, không lấy tùy ý từ client.

### 19.5. Query salary range

~~~javascript
const employees = await encryptedCollection.find({
  tenantId: authenticatedTenantId,
  salary: {
    $gte: 60000,
    $lt: 100000
  }
}).toArray();
~~~

Điều kiện:

- Salary được mã hóa với **QE range**.
- Schema range min/max, numeric BSON type và options đúng.
- Driver/cluster có khả năng range query tương ứng.

Đừng nối thêm sort trên salary hoặc $avg salary vào query rồi mặc định nó vẫn hợp lệ.

### 19.6. Client-side aggregation có giới hạn quy mô

Nếu chỉ có 20 nhân viên trong một phòng ban và policy cho phép, ứng dụng có thể:

1. Lọc tenantId + departmentId trên server.
2. Đọc 20 records có salary được giải mã qua driver.
3. Tính toán tại ứng dụng được cấp quyền.
4. Trả về tổng hợp đã được kiểm soát.

Nếu có **20 triệu nhân viên**, phương án đọc tất cả rồi tính ở client khó chấp nhận về bộ nhớ, network, latency và diện plaintext. Cần quyết định lại threat model hoặc xây **aggregate riêng** có chính sách tiết lộ rõ ràng.

### 19.7. Không biến metadata thành kênh lộ dữ liệu

Một thiết kế sai có thể thêm:

~~~javascript
{
  salaryEncrypted: BinData(/* ... */),
  salaryPlaintextForSorting: 85000
}
~~~

Khi đó mã hóa salaryEncrypted gần như không bảo vệ được giá trị lương nếu bất kỳ người đọc server nào cũng thấy salaryPlaintextForSorting.

Metadata dẫn xuất như **salaryBand**, **hasMedicalNote**, **ageBucket** cũng có thể tiết lộ thông tin. Phải đánh giá **mức độ suy luận** từ các field ấy thay vì cho rằng “không phải salary chính xác thì không nhạy cảm”.

## 20. Khai báo encryptedFields schema cho Queryable Encryption

Để cho phép QE, collection cần một **encryptedFields schema** định nghĩa các field và query types phù hợp, không chỉ đặt một thuộc tính boolean isEncrypted trên document.

### 20.1. Ví dụ schema minh họa

Ví dụ (fragment, không bao gồm toàn bộ cấu hình KMS và ClientEncryption):

~~~javascript
const encryptedFields = {
  fields: [
    {
      path: "identity.taxId",
      bsonType: "string",
      queries: { queryType: "equality" }
    },
    {
      path: "salary",
      bsonType: "int",
      queries: {
        queryType: "range",
        min: 0,
        max: 1000000
      }
    },
    {
      path: "medicalNote",
      bsonType: "string"
    }
  ]
};
~~~

Tùy phiên bản và API:

- Có thể phải/được phép chỉ định **keyId** cho từng field.
- Một số helper có thể tạo **data encryption keys (DEKs)** tự động nếu không có keyId.
- Range options có các yêu cầu cụ thể về **sparsity, trimFactor, precision, min, max**.
- Các field metadata nội bộ và collections liên quan được tạo theo quy trình QE.

**Đừng chạy fragment này như toàn bộ script tạo collection** rồi mong có encryption nếu chưa thiết lập KMS, driver, key vault và encryption helper thích hợp.

### 20.2. Tạo encrypted collection phải dùng quy trình phù hợp

Một workflow:

~~~text
1. Cấu hình MongoDB deployment/edition/version hỗ trợ QE
2. Cấu hình KMS và quyền truy cập keys
3. Tạo hoặc chuẩn bị key vault + DEKs
4. Định nghĩa encryptedFields schema
5. Tạo encrypted collection bằng helper/API được hỗ trợ
6. Tạo/kiểm tra index và metadata collections
7. Cấu hình MongoClient có autoEncryption/explicit mode phù hợp
8. Chỉ sau đó insert/find bằng driver
~~~

Không tự sửa trực tiếp các collection metadata QE bằng CRUD để “dọn chỉ mục”, vì chúng được cơ chế encrypted query quản lý.

### 20.3. Không dùng encryptedFieldsMap tùy tiện trên collection đã có plaintext

Giả sử collection chứa:

~~~javascript
{ taxId: "TAX-000123" } // dữ liệu cũ plaintext
~~~

Sau đó bạn đổi client config để taxId được mã hóa khi ghi dữ liệu mới. Document cũ vẫn plaintext, document mới ciphertext. Query qua encrypted client có thể mã hóa literal thành ciphertext và **không match bản ghi cũ**, khiến kết quả không đầy đủ.

Hơn nữa, lưu lại field cũ plaintext có thể vi phạm chính sách.

Một migration đúng phải:

- Tạo collection đích với schema mới.
- Đọc nguồn qua môi trường bảo vệ.
- Mã hóa/ghi lại mọi document theo quy trình.
- Kiểm tra số lượng, uniqueness, quyền và dữ liệu.
- Chuyển traffic an toàn.
- Xử lý dữ liệu plaintext cũ, backups, cache và exports theo policy.

Không coi **thay config rồi tiếp tục insert** là migration đầy đủ.

### 20.4. QueryType có thể không thay được trên collection hiện có

Một field ban đầu chỉ dùng:

~~~javascript
{ path: "identity.taxId", queries: { queryType: "equality" } }
~~~

Nếu sau này product muốn prefix search, cần đánh giá **tạo schema/index mới và migration**. Không đơn giản thêm queryType prefix trong MongoClient và mong index cũ có đủ tags để trả kết quả.

### 20.5. QE metadata và query indexing

Queryable Encryption có thể tạo **hai collection metadata phụ** cho encrypted queries, thường được mô tả là **ESC** và **ECOC** trong tài liệu kỹ thuật, ngoài collection business.

Mỗi write trên một field queryable có thể phải cập nhật **encrypted query metadata** tương ứng. Với range/string search, số lượng tags/metadata entries có thể nhiều hơn equality.

Điều này giải thích tại sao QE có overhead đáng kể dù ứng dụng chỉ lưu thêm vài encrypted fields.

## 21. Key vault, data encryption keys và KMS

Một hệ thống encrypted fields có ít nhất hai vai trò khóa thường được nhắc tới:

- **DEK – Data Encryption Key:** dùng để mã hóa field data.
- **CMK – Customer Master Key** hoặc key quản lý trên KMS: bảo vệ/wrap các DEKs.

Mô hình khái niệm:

~~~text
KMS / HSM / Key Management Service
            |
            v
         Master Key
            |
            v
  Wrap / unwrap Data Encryption Keys
            |
            v
   Key Vault metadata collection
            |
            v
    Authorized MongoDB driver
            |
            v
   Encrypt / decrypt field values
~~~

### 21.1. MongoDB data access khác key access

Một người có quyền đọc collection MongoDB nhưng không có KMS/key material phù hợp có thể chỉ thấy **BinData ciphertext**.

Ngược lại, một service có khóa giải mã nhưng không kiểm tra quyền của user có thể làm lộ toàn bộ dữ liệu qua API. Không đồng nhất “có key” với “được phép trả field cho người dùng”.

### 21.2. Không hard-code key material

Không ghi:

~~~javascript
const localMasterKey = "base64-secret-master-key-in-repository";
~~~

vào source code production hoặc tài liệu chia sẻ nội bộ.

Ví dụ lab có thể dùng **local KMS provider** theo hướng dẫn MongoDB, nhưng môi trường thật cần chiến lược quản lý keys an toàn, backup, audit và rotation.

### 21.3. Key rotation không đơn thuần là tạo key mới

Trong hệ thống client-side encryption, rotation có thể liên quan:

- Rewrap DEKs bằng master key mới.
- Re-encrypt field data bằng DEK hoặc encryption config mới nếu có thay đổi mạnh hơn.
- Đảm bảo clients cũ/mới cùng hoạt động trong giai đoạn chuyển đổi.
- Không mất quyền giải mã dữ liệu lịch sử.
- Đảm bảo encrypted indexes/metadata được rebuild hoặc chuyển đổi theo yêu cầu.

Tùy loại rotation, thao tác rewrap key metadata có thể **không cần re-encrypt toàn bộ dữ liệu**; nhưng chuyển algorithm/queryType/key IDs có thể yêu cầu migration rộng hơn. Không dùng một script chung cho mọi kiểu key rotation.

### 21.4. Key availability và tính sẵn sàng hệ thống

Nếu KMS tạm thời không truy cập được, ứng dụng có thể:

- Không thể khởi tạo auto encryption client.
- Không thể encrypt write mới.
- Không thể decrypt read cần key chưa cache.
- Trả lỗi hoặc tăng latency do retry.

Cần định nghĩa fallback **không làm hạ mức bảo vệ**; không ghi plaintext tạm vì KMS đang lỗi. Đây là yêu cầu “fail closed” quan trọng với trường được quy định phải mã hóa.

## 22. Java MongoDB Sync Driver: query khi client đã được cấu hình encryption

Ở Java, code nghiệp vụ thường làm việc với **MongoCollection<Document>**, nhưng khả năng mã hóa phụ thuộc **MongoClient** đã được tạo bằng các option encryption phù hợp.

Một MongoClient tạo bằng:

~~~java
MongoClient plain = MongoClients.create(uri);
~~~

**không tự trở thành QE/CSFLE encrypted client** chỉ vì server đang có một collection chứa ciphertext. Để dùng automatic encryption, cần cấu hình **AutoEncryptionSettings**, **keyVaultNamespace**, **kmsProviders**, schema map hoặc encrypted fields map, driver hỗ trợ và thư viện mã hóa theo hướng dẫn chính thức.

Các ví dụ bên dưới cố ý nhận một **MongoCollection đã được cấp từ client mã hóa hợp lệ**. Chúng minh họa hình dạng query và giới hạn nghiệp vụ, không giả định đã tạo KMS/DEKs khi chỉ gọi một hàm Java.

### 22.1. Tìm bằng encrypted equality field

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class SecureTaxIdLookup {
    private final MongoCollection<Document> collection;

    public SecureTaxIdLookup(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public Document findByTaxId(
            String trustedTenantId,
            String taxId) {

        if (trustedTenantId == null || taxId == null) {
            throw new IllegalArgumentException(
                    "tenantId and taxId must be provided");
        }

        return collection.find(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("identity.taxId", taxId)
                )
        ).first();
    }
}
~~~

Đoạn query có thể được driver QE xử lý nếu **identity.taxId** cấu hình queryType equality và môi trường hỗ trợ. Với CSFLE deterministic, logic equality tương tự nhưng client phải dùng schema CSFLE tương ứng.

Nếu taxId được **CSFLE randomized** hoặc **QE queryType none**, truy vấn không tự tìm được theo plaintext.

### 22.2. Range query bằng QE

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;

public final class EncryptedSalaryRangeQuery {
    private final MongoCollection<Document> collection;

    public EncryptedSalaryRangeQuery(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public List<Document> findBetween(
            String trustedTenantId,
            int minimumInclusive,
            int maximumExclusive) {

        if (minimumInclusive < 0
                || maximumExclusive <= minimumInclusive) {
            throw new IllegalArgumentException(
                    "Invalid salary range");
        }

        Bson filter = Filters.and(
                Filters.eq("tenantId", trustedTenantId),
                Filters.gte("salary", minimumInclusive),
                Filters.lt("salary", maximumExclusive)
        );

        return collection.find(filter)
                .limit(100)
                .into(new ArrayList<>());
    }
}
~~~

Để chạy:

- Server và driver phải hỗ trợ **QE range**.
- Field **salary** phải được khai báo queryType range.
- BSON numeric type phải khớp schema (ví dụ **int**).
- Chỉ số 100 là giới hạn response của **dịch vụ minh họa**, không phải ngưỡng do QE tự áp dụng.

Giới hạn query response không làm query trở nên miễn phí; vẫn cần đánh giá khả năng trả hàng loạt bản ghi nhạy cảm và filter tenant.

### 22.3. Update một encrypted field bằng $set

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class SecureSalaryUpdater {
    private final MongoCollection<Document> collection;

    public SecureSalaryUpdater(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public boolean setSalary(
            String trustedTenantId,
            String employeeCode,
            int newSalary) {

        if (newSalary < 0) {
            throw new IllegalArgumentException(
                    "Salary must be nonnegative");
        }

        UpdateResult result = collection.updateOne(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("employeeCode", employeeCode)
                ),
                Updates.set("salary", newSalary)
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

Với QE field salary, driver phải mã hóa **newSalary** trước khi gửi update theo schema. Không thay **Updates.set("salary", value)** bằng **Updates.inc("salary", delta)** nếu salary mã hóa.

**Cảnh báo:** ví dụ này minh họa thao tác cơ bản; trong hệ thống payroll thật cần business authorization, audit, optimistic concurrency, dual approval và transaction policy.

### 22.4. Query bằng field không mã hóa

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public final class MetadataEmployeeSearch {
    private final MongoCollection<Document> collection;

    public MetadataEmployeeSearch(
            MongoCollection<Document> collection) {
        this.collection = collection;
    }

    public List<Document> recentlyCreated(
            String tenantId,
            Date from) {

        return collection.find(
                Filters.and(
                        Filters.eq("tenantId", tenantId),
                        Filters.gte("createdAt", from)
                )
        )
                .sort(Sorts.descending("createdAt"))
                .limit(50)
                .into(new ArrayList<>());
    }
}
~~~

Trong trường hợp này **createdAt** được thiết kế không mã hóa. MongoDB vẫn có thể tận dụng B-tree index có cấu trúc trên tenantId/createdAt; driver giải mã **những encrypted fields được trả về** nếu có quyền.

### 22.5. Không trả raw Document cho mọi user

Một document đã được driver giải mã có thể chứa salary, taxId hoặc medicalNote. API không nên serialize toàn bộ Document vào JSON response nếu người gọi chỉ có quyền xem tên/phòng ban.

Nên:

~~~text
MongoCollection<Document> returns decrypted data
             |
             v
Service applies field-level authorization
             |
             v
Safe response DTO with approved fields
             |
             v
HTTP response
~~~

Driver có khả năng giải mã là **khả năng kỹ thuật của process**, không phải bằng chứng caller được phép xem các field đó.

## 23. Node.js: ranh giới giữa encryption client và query

Đối với MongoDB Node.js Driver, một ứng dụng QE/CSFLE thường cần khởi tạo **MongoClient với autoEncryption options** hoặc dùng **ClientEncryption** theo quy trình explicit encryption.

Một câu lệnh Node.js:

~~~javascript
const collection = encryptedClient
  .db("secure_db")
  .collection("employees");

const employee = await collection.findOne({
  tenantId: authenticatedTenantId,
  "identity.taxId": "TAX-000123"
});
~~~

chỉ có ý nghĩa encrypted equality nếu:

- **encryptedClient** là MongoClient đã được cấu hình QE/CSFLE tương ứng.
- **identity.taxId** được khai báo queryable phù hợp.
- Keys và support library sẵn sàng.
- BSON type của literal đúng với schema.
- Caller có quyền tìm/giải mã kết quả.

### 23.1. Quy trình tạo client theo khái niệm

~~~text
Configuration:
  MONGODB_URI
  Key Vault namespace
  KMS provider(s) and credentials
  Encryption schema/map
  Crypt shared library / auto encryption support
  Driver version and server compatibility

             |
             v
   Create encryption-enabled MongoClient
             |
             v
   Use collections through that client
             |
             v
   Query with supported operators
~~~

Nếu một process chỉ tạo:

~~~javascript
const client = new MongoClient(process.env.MONGODB_URI);
~~~

không truyền cấu hình mã hóa phù hợp, **không thể mặc định nó đã bật QE** dù URI trỏ đúng database.

### 23.2. Không gửi pre-encrypted values tùy ý vào automatic client

Trong automatic encryption, driver thường mong ứng dụng gửi **plaintext values** ở các điểm được schema chỉ định để driver mã hóa. Nếu ứng dụng tự mã hóa rồi đưa ciphertext vào cùng field cho automatic client mã hóa tiếp, có thể gặp lỗi hoặc double-encryption sai mô hình.

Với explicit encryption, ứng dụng tự chịu trách nhiệm payload và query tokens. Hai mode phải được thiết kế có chủ đích, không trộn ngẫu nhiên theo từng code path.

### 23.3. Cơ sở dữ liệu có cả clients mã hóa và không mã hóa

Một hệ thống có:

~~~text
Service A -> encryption-enabled driver
Service B -> ordinary driver
DBA tool  -> ordinary connection
~~~

Phải xác định:

- Service B có quyền ghi field protected không?
- Server có enforcement schema để ngăn plaintext writes không?
- DBA tool có chỉ được đọc ciphertext không?
- Audit log có ghi plaintext từ một tool ngoài không?

Nếu server không cấu hình enforcement phù hợp, một client không mã hóa có thể ghi plaintext vào field lẽ ra phải encrypted, gây vi phạm bảo mật và làm truy vấn QE/CSFLE thiếu dữ liệu.

**Không lấy việc “service chính đã dùng encrypted client” làm bằng chứng toàn bộ collection luôn encrypted.**

## 24. Manual/explicit encryption: trường hợp dùng và rủi ro

Explicit encryption cho phép ứng dụng chủ động:

~~~text
Plaintext value
    |
    v
ClientEncryption.encrypt(value, algorithm/queryType/options)
    |
    v
Encrypted payload
    |
    v
MongoDB insert/find
~~~

### 24.1. Khi nào cân nhắc explicit?

- Cần tích hợp với hệ thống có workflow mã hóa riêng.
- Muốn mã hóa/chỉ định key theo từng operation trong phạm vi được hỗ trợ.
- Ứng dụng đã có tầng bảo mật quản lý ciphertext một cách có kiểm soát.
- Có yêu cầu triển khai/deployment khác với automatic encryption và phiên bản hỗ trợ.

### 24.2. Không tự định nghĩa lại thuật toán

Không nên:

~~~javascript
// Không dùng base64 hay XOR như một giải pháp encryption!
const encrypted = Buffer.from(plaintext).toString("base64");
~~~

Base64 là encoding có thể đảo ngược công khai, **không phải mã hóa bảo mật**. Cũng không tự chế “encrypt” bằng cách trộn salt với SHA-256 rồi coi server đã có encryption queryable.

Sử dụng thuật toán/API được MongoDB cung cấp, đúng key lifecycle và cấu hình.

### 24.3. So sánh ciphertext bằng operator ngoài danh sách

Với explicit CSFLE, server có thể nhìn thấy hai BinData values và thực hiện một số BSON comparisons. Điều đó không có nghĩa kết quả tương ứng với so sánh plaintext.

~~~text
Encrypted value A < encrypted value B
~~~

không suy ra:

~~~text
Plaintext value A < Plaintext value B
~~~

Nếu cần range, hãy dùng QE range đã được thiết kế chính thức. Nếu cần sort/aggregation rộng hơn, phải thay đổi yêu cầu hoặc kiến trúc.

### 24.4. Không dùng explicit encryption để né policy

Một ứng dụng có manual encryption vẫn phải:

- Đảm bảo mọi insert path encrypt đúng field.
- Không cho client không được ủy quyền bypass encryption.
- Không tự sửa metadata QE.
- Giữ key IDs, algorithm, bsonType và queryType nhất quán.
- Không log plaintext/ciphertext có thể suy luận thông tin nhạy cảm.
- Có chính sách re-encrypt và restore.

## 25. Hiệu năng, dung lượng và chi phí Queryable Encryption

Encrypted query có thể truy vấn dữ liệu bí mật nhưng không miễn phí. Với Queryable Encryption, MongoDB cần quản lý metadata/tags và chạy những bước cryptographic query processing tương ứng.

### 25.1. Những thành phần tạo overhead

~~~text
Plaintext document write
          |
          v
Encryption-enabled driver
          |
          v
Encrypted field ciphertext
          |
          +------------------+
          |                  |
          v                  v
 Business document   Encrypted query metadata
          |                  |
          v                  v
   Document write        Metadata/index work
          |                  |
          +---------+--------+
                    |
                    v
            Latency / storage / I/O
~~~

So với collection thường, cần tính:

- Kích thước encrypted payload.
- Số lượng encrypted queryable fields.
- Metadata collections.
- Số tags được tạo cho mỗi field/queryType.
- Thời gian encrypt/decrypt tại driver.
- KMS/key cache và initialization cost.
- Write amplification do index/metadata updates.
- Hiệu quả query khi filter có ít/nhiều matches.

### 25.2. Equality thường ít metadata hơn range/string

Về mặt khái niệm:

~~~text
Equality:
  Tìm đúng một giá trị encrypted
  -> tập metadata có thể tương đối gọn

Range:
  Tìm nhiều mốc giá trị
  -> nhiều cấu trúc/tags cần thiết

Substring:
  Tìm chuỗi con ở nhiều vị trí có thể
  -> metadata/tags có thể tăng nhanh
~~~

Không thể lấy phép đếm tags của equality rồi nhân một hệ số cố định cho mọi range/string queries. Chi phí tùy **giới hạn, precision, độ dài query và các tham số QE**.

### 25.3. String substring có thể tốn nhiều metadata

Với QE String query, số tags có thể tăng theo:

- Độ dài field được mã hóa.
- Độ dài minimum/maximum substring query.
- Giới hạn chuỗi được phép.
- Cách hỗ trợ prefix/suffix so với substring.

Trong thông báo về tính năng GA ở MongoDB 9.0, substring search tập trung vào các String ngắn có giới hạn (ví dụ field dài tối đa 50 ký tự và query term 2–6 ký tự theo giới hạn công bố). **Không nên hiểu substring QE là full-text search trên một mô tả dài hàng nghìn ký tự**.

Hãy đọc đúng giới hạn phiên bản và ước lượng storage trước khi bật substring query trên nhiều field.

### 25.4. Range: min/max/precision/sparsity/trimFactor

Một field salary được mã hóa với range QE:

~~~javascript
{
  path: "salary",
  bsonType: "int",
  queries: {
    queryType: "range",
    min: 0,
    max: 1000000
  }
}
~~~

Các tham số cấu hình liên quan (tùy version):

| Tham số | Vai trò |
|---|---|
| min, max | Ràng buộc miền giá trị có thể query |
| precision | Giới hạn độ chính xác thập phân cho double/decimal theo rule |
| sparsity | Trade-off giữa mật độ encrypted range metadata và chi phí/truy vấn |
| trimFactor | Ảnh hưởng cách range index/tags được tạo và overhead |
| contention | Giúp điều chỉnh hành vi/chi phí khi có các thao tác đồng thời |

**Không tự tối ưu bằng cách chọn các con số ngẫu nhiên**; mỗi tham số có ràng buộc, hiệu ứng và giới hạn thay đổi riêng. Phải đo trên workload thực tế và đối chiếu tài liệu của server đang chạy.

### 25.5. Precision không phải làm tròn số gốc theo yêu cầu nghiệp vụ

Trong một số cấu hình QE range double/decimal, precision ảnh hưởng **giá trị dùng để truy vấn và tạo range index**; nó có thể cắt bớt chữ số thập phân chứ không đơn giản làm tròn theo quy tắc nghiệp vụ.

Ví dụ:

~~~text
Original stored encrypted value: 10.18
Index/query precision = 1
Relevant query representation: 10.1
~~~

Đừng xây logic tính tiền lương, thuế hoặc lãi dựa trên một assumption sai về làm tròn. Khi nghiệp vụ cần decimal chính xác, chọn Decimal128 hoặc integer minor units và query range configuration phù hợp.

### 25.6. Metadata cleanup và compaction

Trong QE, các collection metadata có thể tăng kích thước khi có nhiều insert/update/delete. Tài liệu có các quy trình **compaction/cleanup encrypted data** riêng.

Không dùng:

~~~javascript
// Không tự sửa metadata QE:
db.enxcol_.deleteMany({});
~~~

hoặc đổi tên những namespace nội bộ mà không theo công cụ hỗ trợ. Vận hành cần:

- Theo dõi metadata storage.
- Chạy các lệnh compaction/cleanup theo version và runbook.
- Tránh chạy đồng thời với những migration lớn nếu chưa đánh giá tải.
- Hiểu thay đổi này có thể ảnh hưởng thời gian thực thi truy vấn.

### 25.7. Diagnose query latency

Nếu encrypted equality query chậm:

1. Xác nhận query dùng đúng queryType/schema.
2. Xem filter tenant có được áp dụng không.
3. Kiểm tra độ chọn lọc của query.
4. Kiểm tra metadata/index trạng thái chuẩn.
5. Đo latency encrypt/decrypt ở driver.
6. Đo latency MongoDB query/round trip.
7. Quan sát write load và metadata growth.
8. Kiểm tra server/driver version.

Đừng cho rằng mọi chậm trễ do B-tree index thiếu trên encrypted field; tạo thêm index đó với QE còn có thể làm hiệu năng tệ hơn.

## 26. Quan sát và logging khi dùng encrypted fields

### 26.1. Log có thể bị redacted

Để tránh lộ thông tin nhạy cảm, Queryable Encryption có các quy tắc **redaction** trên query logs/profiler/diagnostic commands. Một số thông tin thường thấy ở collection plaintext có thể bị ẩn hoặc bỏ qua.

Điều này bảo vệ bảo mật nhưng khiến việc debug dựa hoàn toàn vào MongoDB slow-query log khó hơn.

### 26.2. Application metrics nên ghi gì?

| Metric gợi ý | Mục đích |
|---|---|
| encrypted_query_latency_p95 | Độ trễ từ góc nhìn ứng dụng |
| query_type | Equality/range/string/none workflow |
| encrypted_write_latency_p95 | Chi phí ghi qua encrypted client |
| decrypt_latency_p95 | Thời gian giải mã nếu được instrument an toàn |
| kms_errors | Lỗi/timeout tới KMS |
| encryption_schema_mismatch | Client/schema/version không khớp |
| unsupported_operator_errors | Query không được hỗ trợ |
| bson_type_mismatch | Literal/query/field sai kiểu |
| metadata_storage_bytes | Tăng trưởng metadata QE |
| encrypted_collection_migration_progress | Tiến độ migration |
| plaintext_write_incidents | Số sự cố ghi plaintext trái policy |
| unauthorized_decrypt_attempts | Các hành vi truy cập trái quyền |

Các tên là **metric ứng dụng được đề xuất**, không phải MongoDB tự xuất nguyên các key như trên.

### 26.3. Không log giá trị mật

Không log:

~~~text
taxId plaintext: TAX-000123
salary plaintext: 85000
decrypted full Document: ...
KMS secret / local master key / DEK material
~~~

Thay vào đó có thể log:

~~~text
requestId
tenantRef (scope được phép)
collection
queryType
operator family
model/schema version
latency
error code/category
key reference (không log key material)
~~~

Ngay cả ciphertext/tags cũng có thể là dữ liệu nhạy cảm trong một threat model nhất định; không đẩy toàn bộ encrypted payload vào observability pipeline vì nghĩ “đã mã hóa nên an toàn”.

### 26.4. Explain và profiler

Một số lệnh chẩn đoán có thông tin hạn chế/redacted với QE. **Explain output trên encrypted collections có thể khác hoặc ít thông tin hơn** cách debug query plaintext.

Nếu query chậm, dùng:

- Metrics ở ứng dụng/driver.
- Query plan/index metadata được phép xem.
- Quan sát tài nguyên cluster.
- Tài liệu QE profiler/log redaction.
- Một môi trường test có data giả lập, tránh đưa plaintext production vào hệ thống debug.

Không tắt mã hóa trên production chỉ để thu log dễ hơn.

### 26.5. Monitoring không được làm lộ quyền dữ liệu

Một dashboard theo tenantId có thể bản thân chứa metadata nhạy cảm. Nếu user không có quyền xem số lượng nhân viên/giá trị giao dịch của tenant khác, dashboard tổng hợp cũng cần authorization và access scope.

Mã hóa field salary không giúp nếu monitoring công khai bảng **salaryBandCount per tenant** có thể tiết lộ salary distribution trái policy.

## 27. Migration từ plaintext hoặc CSFLE sang QE

Giả sử collection cũ:

~~~javascript
{
  employeeCode: "E-1001",
  salary: 85000
}
~~~

muốn chuyển thành:

~~~javascript
{
  employeeCode: "E-1001",
  salary: BinData(/* QE range */)
}
~~~

### 27.1. Các điều kiện cần chuẩn bị

1. Xác định **những field phải encrypt** và queryType từng field.
2. Đánh giá version/edition/driver/crypt support.
3. Kiểm kê mọi code path đọc/ghi, batch jobs, ETL, backup và reporting.
4. Chuẩn bị KMS/DEKs và quyền của service.
5. Thiết kế collection đích được tạo bằng **encryptedFields schema**.
6. Tính storage/tags/index metadata và capacity.
7. Chọn phương án downtime/dual-write/cutover.
8. Có checklist xác minh và rollback/restore.

### 27.2. Quy trình tổng quát

~~~text
Plaintext / old CSFLE collection
              |
              v
Authorized migration reader
              |
              v
Validate types + business invariants
              |
              v
Authorized QE-enabled writer
              |
              v
New QE collection + metadata
              |
              v
Compare counts / sample values / query results
              |
              v
Switch application traffic
              |
              v
Retire old collection and copies by policy
~~~

### 27.3. Không sửa encryptedFieldsMap tại runtime rồi mong tự migrate

Tài liệu MongoDB cảnh báo việc thay **encryptedFieldsMap** của client và để plaintext records cũ tồn tại sẽ gây mismatch. Query từ client mới có thể mã hóa literal và không match document cũ.

Cách an toàn hơn là **versioned migration** có ghi và xác nhận vào collection đích, không chỉ thay một biến cấu hình.

### 27.4. Xử lý traffic trong lúc migration

Nếu ứng dụng vẫn ghi vào collection cũ trong lúc di chuyển, có nguy cơ mất hoặc trùng updates. Các chiến lược có thể:

- Tạm dừng write với maintenance window.
- Change capture/dual-write được thiết kế và kiểm tra kỹ theo tính năng được hỗ trợ.
- Migrate theo checkpoint với replay và reconciliation.

Lưu ý **QE có hạn chế về change streams/commands**, nên không mặc định một connector CDC thông thường đã giải mã/di chuyển được mọi encrypted field.

### 27.5. Phép kiểm nghiệm cần dựa trên business invariants

Không chỉ đối chiếu:

~~~text
Old count = 100000
New count = 100000
~~~

Mà còn:

- Những field cần encrypt có ciphertext chứ không còn plaintext.
- Client có quyền decrypt trả đúng giá trị gốc.
- Client không có quyền không xem được plaintext.
- Query equality/range/string trả cùng tập kết quả mong đợi (theo feature).
- Unique business constraints vẫn được thực thi.
- Tenant isolation không thay đổi.
- Index/metadata readiness đạt yêu cầu.
- Báo cáo/ETL được chuyển sang thiết kế mới.

### 27.6. Cần xử lý dữ liệu cũ trên backup/log

Ngay cả khi encrypted collection mới đã đúng, collection cũ và backup trước migration có thể còn plaintext. Việc xóa/retention/restore phải theo chính sách của doanh nghiệp; không tự xóa backup cần thiết cho khôi phục mà chưa có phê duyệt.

## 28. Các điểm mới và khác biệt theo phiên bản

Một số điểm mốc cần ghi nhớ khi đọc tài liệu:

| Nhánh tính năng | Điều cần kiểm tra |
|---|---|
| CSFLE deterministic/randomized | Query equality/hạn chế theo driver/algorithm |
| QE equality | Có từ các phiên bản QE ban đầu, yêu cầu encryptedFields schema |
| QE range | Hỗ trợ chính thức từ MongoDB 8.0; các phiên bản cũ có trạng thái/hạn chế khác |
| QE prefix/suffix/substring | Public preview trên MongoDB 8.2; GA trên MongoDB 9.0 |
| QE String algorithm | Cấu hình mới trong 9.0 khác các kiểu preview cũ |
| $lookup với nhiều encrypted collections | Hỗ trợ và giới hạn thay đổi theo phiên bản, đặc biệt từ 8.1 |
| Range tuning | Giới hạn sparsity/trimFactor/precision có thể thay đổi theo release |
| Driver/crypt shared library | Cần đúng khả năng queryType; không chỉ version server |
| MongoDB Atlas/Enterprise/Community | Tính năng automatic/explicit và deployment support khác nhau |

### 28.1. Không khẳng định “MongoDB không bao giờ tìm substring trên encrypted field”

Nhận định này đúng với CSFLE truyền thống và các phiên bản QE chưa có tính năng String search, **nhưng không đúng như một tuyên bố vĩnh viễn cho MongoDB 9.0**.

Ngược lại, nhận định “MongoDB có substring QE nên mọi collection MongoDB đều tìm regex trên encrypted field được” cũng sai: cần queryType/schema, loại String, hạn độ dài, version và driver phù hợp.

### 28.2. Dùng tài liệu đúng phiên bản để chọn syntax

Khi hệ thống chạy 7.0, đừng lấy ví dụ 9.0 rồi chạy ngay. Khi đã nâng từ 8.2 preview lên 9.0, đừng giữ các tên query types/algorithm preview mà không đọc hướng dẫn tương thích.

Trong một ADR (Architecture Decision Record), nên ghi rõ:

~~~text
MongoDB server version:
FCV:
MongoDB driver version:
Crypt shared library version:
QE/CSFLE mode:
QueryType per encrypted field:
KMS provider:
Key vault namespace:
Schema/index migration version:
~~~

Một hệ thống có encryption không nên chỉ có tài liệu “dùng MongoDB và có mã hóa field” mà thiếu các thông tin xác định compatibility.

## 29. Các lỗi và tình huống thường gặp

### 29.1. Truy vấn CSFLE equality trả về 0 dù nhìn thấy ciphertext

**Triệu chứng:** findOne theo taxId không trả document, nhưng query theo _id cho thấy field taxId là BinData.

Khả năng:

- Query chạy bằng MongoClient **không cấu hình CSFLE/QE**.
- Field dùng randomized CSFLE hoặc QE queryType none.
- Query value có BSON type/normalization khác khi mã hóa.
- Document được mã hóa bằng key/schema/version khác.
- Một số document cũ vẫn plaintext sau khi bật encryption.

**Hướng xử lý:** kiểm tra encryption client, encryptedFields/schema, key ID, BSON type và một record mẫu qua client có quyền. Không giải quyết bằng cách thử mọi ciphertext trong production.

### 29.2. $gt salary trả sai hoặc báo lỗi

**Nguyên nhân:** field dùng CSFLE deterministic/randomized, nhưng server được yêu cầu so sánh numerical value trên ciphertext.

**Hướng xử lý:** nếu cần range ở server, thiết kế QE range trên version hỗ trợ; nếu workload nhỏ và policy cho phép, lọc trước theo metadata và xử lý ở client đã giải mã.

### 29.3. Sort salary cho kết quả không hợp lý

**Nguyên nhân:** ciphertext không bảo toàn numerical order. Kể cả QE range cho phép filter, nó không tự cho phép sort plaintext salary.

**Hướng xử lý:** đổi sort sang field không mã hóa được phê duyệt, hoặc thiết kế báo cáo/tính toán bên phía client có giới hạn dữ liệu.

### 29.4. Unique index trên encrypted email không chặn trùng

**Nguyên nhân:** QE/randomized ciphertext khác nhau cho cùng email, nên unique index thấy những giá trị khác nhau.

**Hướng xử lý:** thiết kế atomic registry/business uniqueness riêng, hoặc một lookup token an toàn đã được review, phù hợp threat model. Không coi check-before-insert là biện pháp tránh race.

### 29.5. Regex trên encrypted name bị từ chối

**Nguyên nhân:** CSFLE không hỗ trợ regex trên plaintext encrypted field; QE equality/range cũng không tự cho phép regex.

**Hướng xử lý:** nếu yêu cầu thật là prefix/suffix/substring, kiểm tra QE String query của phiên bản phù hợp và chi phí của nó. Nếu cần full-text search, đánh giá kiến trúc khác, không âm thầm lưu name plaintext để index.

### 29.6. Queryable Encryption index lớn ngoài dự kiến

**Nguyên nhân:** quá nhiều queryable encrypted fields, range độ chính xác quá cao, substring queries có metadata tags lớn hoặc chưa chạy cleanup/compaction phù hợp.

**Hướng xử lý:** đo metadata storage và write amplification, giới hạn queryType/precision/sparsity theo policy, cân nhắc tách các field không cần query về queryType none.

### 29.7. QE collection chậm sau nhiều cập nhật

**Nguyên nhân có thể:** metadata growth, nhiều encrypted index updates, contention, filter kém chọn lọc hoặc KMS/driver latency.

**Hướng xử lý:** instrument từng bước, xem encrypted metadata maintenance và query options. Không tạo B-tree index trên encrypted field để “chữa chậm” theo thói quen.

### 29.8. Array of objects không thể query như thường

**Nguyên nhân:** encrypted array hoặc nested encrypted field trong array chịu giới hạn; server không có các phần tử plaintext để multikey indexing/elemMatch tùy ý.

**Hướng xử lý:** tách child documents theo mô hình được hỗ trợ hoặc đổi yêu cầu query. Không thêm index vào một field BinData mà kỳ vọng tạo ra plaintext child index.

### 29.9. Query chạy tốt qua service A nhưng lỗi qua service B

Khả năng:

- Hai service dùng MongoDB driver/crypt library version khác nhau.
- Một service dùng encryption-enabled client, service kia dùng ordinary client.
- Encryption schema/key vault cấu hình khác.
- Service B đang dùng operator không được support.
- Query literal có kiểu BSON khác nhau.

**Hướng xử lý:** so sánh cấu hình, package versions, KMS access và schema version, không chỉ so SQL-like query shape.

### 29.10. Client không decrypt được sau rotation

**Nguyên nhân:** service không có key mới, key vault/kms config sai, DEK không thể unwrap hoặc một bước migration đã thay encryption key không nhất quán.

**Hướng xử lý:** kiểm tra key reference/permissions, phiên bản rotation và quy trình backup/restore; không đưa DEK/master key vào log để debug.

### 29.11. $lookup trên encrypted key không khớp

**Nguyên nhân:** join trên encrypted field chịu hạn chế; không được suy ra ciphertext của hai collection có ý nghĩa join như plaintext.

**Hướng xử lý:** dùng opaque reference không nhạy cảm làm join key, hoặc pipeline được chính xác phiên bản/driver hỗ trợ với giới hạn tương ứng.

### 29.12. Tính average salary bằng aggregation trả null/sai

**Nguyên nhân:** server đang xử lý BinData ciphertext, không có Number plaintext.

**Hướng xử lý:** thiết kế một quy trình tính toán bên client được ủy quyền hoặc một kho aggregate được phê duyệt, không tự phát lộ plaintext salary trong collection.

### 29.13. Một field không mã hóa vẫn bị lỗi $text

Trong một số chế độ automatic encryption, driver chặn các operator như **$text, $where, $jsonSchema** dù query không trực tiếp nhắm field đã mã hóa.

**Hướng xử lý:** xem danh sách supported operations của **MongoClient đã cấu hình encryption**; cân nhắc tách query service/collection nếu cần Search và không thể kết hợp an toàn trong cùng pipeline.

### 29.14. Không đổi được queryType từ equality sang range

**Nguyên nhân:** encryptedFields schema/index được thiết kế cho một queryType đã khai báo và có ràng buộc immutability.

**Hướng xử lý:** versioned migration sang collection/schema phù hợp, backfill và cutover. Không sửa local encryptedFieldsMap giữa chừng rồi mong metadata index tự xây lại.

### 29.15. Report có dữ liệu bí mật dù DB đã encrypt

**Nguyên nhân:** API/reporting service có quyền decrypt đã xuất plaintext sang cache, warehouse hoặc log không được bảo vệ.

**Hướng xử lý:** kiểm kê data flow, áp dụng field-level authorization và retention ở mọi downstream system. Mã hóa MongoDB không loại bỏ rủi ro từ các ứng dụng được phép giải mã.

### 29.16. KMS lỗi khiến một số request thất bại

**Nguyên nhân:** khởi tạo key không thành công, key reference không đủ quyền, provider timeout hoặc key cache chưa có dữ liệu.

**Hướng xử lý:** retry có giới hạn, health check và fail closed. Không chuyển sang ghi plaintext “tạm” để giữ availability nếu chính sách yêu cầu field encryption.

## 30. Runbook kiểm tra một truy vấn trên encrypted field

### Bước 1 — Xác định mô hình mã hóa

Ghi:

~~~text
Collection:
Field path:
Encryption: CSFLE deterministic / randomized / QE
QueryType:
BSON type:
Driver version:
Server version:
Key ID:
~~~

### Bước 2 — Xác định thao tác cần làm

Ví dụ:

~~~text
exact match taxId
salary numeric range
sort by salary
calculate average salary
prefix name search
join by customer ID
~~~

Đối chiếu với **supported operators/aggregation expressions**. Nếu thao tác không được hỗ trợ, không cố gửi cùng query tới server rồi hy vọng kết quả đúng.

### Bước 3 — Kiểm tra index và schema

- CSFLE deterministic equality có index phù hợp không?
- QE đã khai báo queryType đúng chưa?
- QE metadata collections/index đã được tạo đúng chưa?
- Đã vô tình thêm B-tree index trên QE encrypted field không?
- Dùng field metadata không mã hóa có đủ cho routing/filter/sort không?

### Bước 4 — Kiểm tra client

- Có thực sự dùng encryption-enabled MongoClient không?
- KMS key vault/DEK/config có phù hợp không?
- Có trộn explicit và automatic encryption sai cách không?
- BSON type của query value có khớp không?

### Bước 5 — Kiểm tra quyền

- Tenant context lấy từ authentication không?
- User có quyền search/decrypt field không?
- API có gửi thêm plaintext vào log/cache không?
- Dữ liệu vừa migration có đồng bộ hoàn chỉnh chưa?

### Bước 6 — Đo hiệu năng theo tầng

~~~text
Authentication/authorization
            |
            v
Driver encryption/query analysis
            |
            v
Network + MongoDB query
            |
            v
Driver decryption
            |
            v
Response transformation
~~~

Đo latency ở các chặng khác nhau, không gộp hết rồi tự quy kết thiếu index.

### Bước 7 — Kết luận và chọn giải pháp

Phân loại:

- **Unsupported query pattern** → đổi queryType/schema/kiến trúc.
- **Wrong encryption client** → sửa cấu hình driver/KMS.
- **Wrong BSON type** → sửa serialization/validation.
- **Missing query index/metadata** → sửa quy trình tạo collection.
- **Metadata/index overhead** → tối ưu theo hướng dẫn QE.
- **Permission leak** → xử lý như sự cố bảo mật.
- **Migration inconsistency** → đối soát và phục hồi theo runbook.

Tất cả thao tác thay đổi encryption schema hoặc cleanup metadata production cần quyền và phê duyệt phù hợp.

## 31. Những quyết định kiến trúc có thể thay cho query trên encrypted field

### 31.1. Query bằng opaque ID

~~~text
User provides customerCode
          |
          v
MongoDB exact match on opaque customerCode
          |
          v
Driver decrypts secret profile
~~~

Phù hợp khi người dùng đã có một ID công khai không mang ý nghĩa nhạy cảm.

### 31.2. Query theo metadata được phép

~~~text
tenantId + createdAt + status
          |
          v
Narrow bounded result set
          |
          v
Authorized client decrypts selected fields
~~~

Chỉ phù hợp nếu policy chấp nhận metadata và nếu số records đủ nhỏ.

### 31.3. Tách thông tin cần Search khỏi bí mật

Một collection có thể giữ:

~~~javascript
{
  docRef: "DOC-1001",
  publicTitle: "Hướng dẫn quy trình",
  encryptedContent: BinData(/* confidential */)
}
~~~

Hệ thống tìm trên **publicTitle** nếu nó thực sự được phép công khai, rồi decrypt nội dung sau khi kiểm quyền.

**Không được tạo publicTitle từ một bí mật** mà không đánh giá mức độ tiết lộ.

### 31.4. Dedicated application-side computation

Nếu cần tính một phép tổng hợp rất nhạy cảm nhưng dataset nhỏ:

~~~text
Authorized batch
  -> query by approved nonsecret selectors
  -> decrypt records
  -> compute in protected runtime
  -> output approved aggregate only
~~~

Cần bảo vệ memory/logs, kiểm soát export và bảo đảm dataset đủ nhỏ để xử lý ổn định.

### 31.5. Đổi yêu cầu sản phẩm

Đôi khi câu trả lời tốt nhất là **không xây chức năng search theo toàn bộ field nhạy cảm**. Ví dụ:

- Không cần tìm mọi medicalNote chứa một từ bất kỳ.
- Không cần sort toàn công ty theo lương từ cao xuống thấp.
- Không cần autocomplete trên số tài khoản đầy đủ.

Thay vì ép database phá một ràng buộc bảo mật, có thể đổi UI/workflow để user xác định hồ sơ bằng một mã opaque rồi xem nội dung có quyền.

## 32. Bài tập thực hành và tình huống

Các bài tập chủ yếu kiểm tra **khả năng phân tích thiết kế và giới hạn**. Để thực hành QE/CSFLE trực tiếp, phải có MongoDB deployment/driver/KMS được cấu hình hợp lệ; không chạy các lệnh thay schema hoặc mã hóa trực tiếp trên collection chứa dữ liệu thật.

### Bài 1. Phân biệt các lớp mã hóa

Một hệ thống có TLS và encryption at rest nhưng vẫn lưu trường salary dưới dạng số 85000 trong document bình thường.

**Câu hỏi:** MongoDB server có thể thực hiện $avg salary không? Điều này có đồng nghĩa salary được mã hóa phía client không?

**Đáp án:** Server vẫn có thể xử lý salary plaintext ở tầng database, nên aggregation số học có thể hoạt động theo các điều kiện MongoDB thông thường. Nhưng salary **chưa được client-side field encrypt**; TLS và encryption at rest bảo vệ những lớp khác.

### Bài 2. Deterministic hay randomized?

Ứng dụng cần:

~~~text
taxId: tìm chính xác theo giá trị
medicalNote: chỉ đọc sau khi đã biết employeeCode
~~~

**Câu hỏi:** Nếu dùng CSFLE, bạn sẽ cân nhắc algorithm nào cho từng trường?

**Định hướng:** taxId có thể dùng deterministic để hỗ trợ equality nếu chấp nhận leakage và các giới hạn; medicalNote nên cân nhắc randomized vì không cần query theo plaintext. Cần đánh giá cardinality, model quyền và khóa trước khi quyết định.

### Bài 3. Frequency analysis

Một field deterministically encrypted có ba plaintext values, phân bố lần lượt 90%, 9% và 1%.

**Câu hỏi:** Mã hóa có che hoàn toàn tần suất của từng giá trị không?

**Đáp án:** Không. Cùng plaintext sinh cùng ciphertext trong deterministic CSFLE, nên phân bố ciphertext có thể bộc lộ các nhóm giá trị và cho phép suy luận.

### Bài 4. Randomized equality

Hai document có cùng:

~~~text
medicalNote plaintext = "allergy"
~~~

nhưng ciphertext khác nhau. Một lập trình viên tạo index trên medicalNote rồi tìm chính xác chuỗi "allergy".

**Câu hỏi:** Index này có giúp tìm được cả hai document theo plaintext không?

**Đáp án:** Không. Index trên randomized ciphertext không tạo khả năng equality lookup plaintext. Cần đổi query architecture hoặc chọn encryption scheme hỗ trợ query phù hợp.

### Bài 5. QE equality

Field **identity.taxId** khai báo:

~~~javascript
{
  path: "identity.taxId",
  bsonType: "string",
  queries: {
    queryType: "equality"
  }
}
~~~

**Câu hỏi:** Với client được cấu hình QE, có thể tìm taxId bằng equality không? Có thể tự tìm salary range trên field đó không?

**Đáp án:** Equality được hỗ trợ theo schema và kiểu BSON; điều đó không cho phép range query trên String taxId. Cần field/queryType khác nếu muốn thao tác range.

### Bài 6. Range QE và sắp xếp

Collection có **salary** cấu hình QE range. Product muốn:

1. Tìm salary từ 60000 đến 100000.
2. Sắp xếp toàn bộ kết quả giảm dần theo salary.

**Câu hỏi:** Hai thao tác này có được bảo đảm đồng thời không?

**Đáp án:** Range filter được hỗ trợ ở version/schema phù hợp. **Sort theo plaintext salary không tự được hỗ trợ** chỉ vì đã có range query; phải chọn hướng xử lý khác nếu cần sort.

### Bài 7. QE string search theo phiên bản

Hệ thống MongoDB 7.0 yêu cầu tìm suffix của encrypted account number. Nhóm phát triển đọc bài viết MongoDB 9.0 về QE String GA.

**Câu hỏi:** Có thể copy syntax vào 7.0 không?

**Đáp án:** Không. Hỗ trợ prefix/suffix/substring khác theo phiên bản: bản 8.2 có public preview; 9.0 có GA. Cần nâng cấp tương thích hoặc đổi thiết kế, không assume feature có ở 7.0.

### Bài 8. $regex trên ciphertext

~~~javascript
db.records.find({
  encryptedName: /^Nguyen/
});
~~~

**Câu hỏi:** Regex có thể tìm trực tiếp trong encrypted field không?

**Đáp án:** Không như một phép tìm String plaintext thông thường. CSFLE không hỗ trợ regex plaintext trên ciphertext. Trong QE mới, cần **queryType String tương ứng và toán tử được hỗ trợ**, không phải regex tùy ý.

### Bài 9. Tạo index sai cho QE

Một developer tạo:

~~~javascript
db.records.createIndex({
  encryptedSalary: 1
});
~~~

trên QE encryptedSalary vì query range chậm.

**Câu hỏi:** Đây có phải hướng index được tài liệu khuyến nghị không?

**Đáp án:** Không. QE dùng encrypted query index/metadata chuyên biệt. Tạo index thường trên encrypted field có thể làm giảm hiệu năng. Cần kiểm tra encryptedFields schema, queryType, metadata và tuning đúng version.

### Bài 10. __safeContent__

Một nhóm muốn sửa trực tiếp **__safeContent__** để làm kết quả QE xuất hiện nhiều hơn.

**Câu hỏi:** Có nên không?

**Đáp án:** Không. __safeContent__ và metadata liên quan thuộc cơ chế QE; không chỉnh tùy tiện. Khi cần index/tối ưu, làm theo tài liệu/version và công cụ được hỗ trợ.

### Bài 11. Unique plaintext trên QE

Hai customer có email plaintext giống nhau, nhưng QE ciphertext khác nhau. Unique index được đặt trên encryptedEmail.

**Câu hỏi:** Unique index đó có bảo đảm không trùng email gốc không?

**Đáp án:** Không. MongoDB so sánh encrypted index keys, không phải một plaintext uniqueness invariant. Cần atomic business uniqueness riêng hoặc cryptographic lookup pattern đã được review.

### Bài 12. Race condition của check-before-insert

Hai request đồng thời đều chạy find(email) không thấy, rồi cùng insert.

**Câu hỏi:** Có cách nào tránh race chỉ bằng find trước insert không?

**Đáp án:** Không. Cần một atomic uniqueness primitive hoặc một workflow concurrency-safe thích hợp, và vẫn phải bảo vệ thông tin email. Mã hóa tự nó không giải quyết race.

### Bài 13. Shard key bí mật

Một collection QE có encrypted taxId. DBA định chọn **taxId** làm shard key để phân bố tài liệu.

**Câu hỏi:** Có phù hợp không?

**Đáp án:** Không. QE encrypted field không được dùng làm shard key. Cần chọn một opaque, unencrypted shard key được policy cho phép và đáp ứng query/capacity requirements.

### Bài 14. $avg trên encrypted salary

Một query:

~~~javascript
db.employees.aggregate([
  {
    $group: {
      _id: "$departmentId",
      avgSalary: { $avg: "$salary" }
    }
  }
]);
~~~

**Câu hỏi:** Nếu salary là ciphertext, MongoDB có thể tính chính xác average salary plaintext không?

**Đáp án:** Không theo ngữ nghĩa aggregation số học thông thường. Cần một hệ thống tính toán ở client được ủy quyền hoặc aggregate riêng được phê duyệt.

### Bài 15. $inc một field QE

~~~javascript
await encryptedCollection.updateOne(
  { employeeCode: "E-1001" },
  { $inc: { salary: 5000 } }
);
~~~

**Câu hỏi:** Vì sao không phù hợp với salary encrypted?

**Đáp án:** $inc đòi server tính cộng trên giá trị Number hiện có. Server không có salary plaintext; QE automatic encryption chỉ hỗ trợ những update operators nhất định như $set/$unset trên encrypted field. Có thể đọc/giải mã, tính tại client và cập nhật bằng $set với version condition.

### Bài 16. Null trên encrypted field

Ứng dụng thực hiện:

~~~javascript
await encryptedCollection.findOne({
  "identity.taxId": null
});
~~~

**Câu hỏi:** Có thể mặc định điều kiện null được encrypted query support không?

**Đáp án:** Không. Query comparison với null trên encrypted field có thể bị từ chối. Nên phân biệt field missing, optional field và metadata hợp lệ theo threat model.

### Bài 17. Array of documents

~~~javascript
{
  contacts: [
    { type: "WORK", phone: "+84..." },
    { type: "HOME", phone: "+84..." }
  ]
}
~~~

**Câu hỏi:** Một collection mã hóa randomized toàn contacts có thể dùng multikey index để tìm từng phone plaintext không?

**Đáp án:** Không. Encrypted array được server xem như ciphertext; không tự tạo index plaintext theo phần tử. Có thể tách child documents hoặc chọn mô hình query khác.

### Bài 18. QE upsert với encrypted filter

Code:

~~~javascript
await encryptedCollection.updateOne(
  { "identity.taxId": "TAX-1001" },
  { $set: { status: "ACTIVE" } },
  { upsert: true }
);
~~~

**Câu hỏi:** Có thể mặc định document mới được insert có identity.taxId không?

**Đáp án:** Không. QE có giới hạn về encrypted fields trong upsert filter; các field đó có thể không được đưa vào inserted document. Cần chủ động thiết kế insert payload và invariant, và không dùng upsert thay unique constraint.

### Bài 19. Sort sau khi giải mã một trang

Ứng dụng đọc 20 records đầu tiên theo createdAt, decrypt salary rồi sort 20 records đó, sau đó tuyên bố “20 người lương cao nhất toàn hệ thống”.

**Câu hỏi:** Sai ở đâu?

**Đáp án:** 20 records đã lấy chỉ là một **subset theo createdAt**, không phải toàn bộ tập cần xét; sort cục bộ không trả top-salary toàn collection. Cần thiết kế lại truy vấn, data flow hoặc nghiệp vụ.

### Bài 20. Collation case-insensitive

Field email deterministic encrypt. Một developer thêm collation strength=2 rồi cho rằng "Alice@example.com" và "alice@example.com" sẽ match.

**Câu hỏi:** Có thể tin kết quả không?

**Đáp án:** Không. Collation MongoDB không tự áp dụng ngữ nghĩa String plaintext trên ciphertext. Nếu cần canonical equality, ứng dụng phải có quy tắc normalization đúng nghiệp vụ và áp dụng nhất quán trước khi encrypt.

### Bài 21. Client không có keys

Một DBA có quyền đọc MongoDB collection nhưng không có DEK/KMS access.

**Câu hỏi:** DBA có thể đọc plaintext của field client-side encrypted trực tiếp từ server không?

**Đáp án:** Theo thiết kế, server chỉ lưu ciphertext; một client không có khả năng decrypt thích hợp không tự thấy plaintext. Nhưng quyền đọc metadata và khả năng suy luận vẫn phải được đánh giá; không coi đây là lý do bỏ role-based access controls.

### Bài 22. Metadata của QE tăng mạnh

Một collection có ba fields queryable String substring, writes tăng nhanh và metadata storage vượt dự kiến.

**Câu hỏi:** Có những hướng điều tra nào?

**Định hướng:** Xem giới hạn/version của substring queries, số tags theo độ dài, cấu hình query length/field length, volume ghi, metadata compaction/cleanup và nhu cầu thực sự có phải substring search trên cả ba fields hay không.

### Bài 23. Đổi QE queryType không migration

Field salary ban đầu QE equality/none. Product muốn range và team chỉ đổi cấu hình local encryptedFieldsMap.

**Câu hỏi:** Vì sao có thể sai?

**Đáp án:** Query type là một phần của schema/index metadata và có ràng buộc thay đổi. Dữ liệu/index cũ không tự được chuyển sang khả năng range mới. Cần versioned collection migration/backfill và cutover phù hợp.

### Bài 24. Dùng $lookup với encrypted join key

Hai collection orders/customers cùng có encrypted customerId.

**Câu hỏi:** Có thể mặc định $lookup localField/foreignField trên customerId hoạt động như plaintext không?

**Đáp án:** Không. QE/CSFLE có những giới hạn join trên encrypted fields; một số version có self-join hoặc multiple encrypted collections behavior riêng. Thiết kế đơn giản hơn là dùng opaque reference không nhạy cảm khi policy cho phép.

### Bài 25. Truy vấn String prefix từ phiên bản mới

Ứng dụng MongoDB 9.0 cần search encrypted case number theo prefix "CASE-2026-". Một developer dùng regex.

**Câu hỏi:** Cần điều kiện gì để sử dụng khả năng QE String mới?

**Định hướng:** Chọn queryType prefix với thuật toán/string schema đúng 9.0, tham số case/diacritic/length hợp lệ, driver và crypt shared library hỗ trợ. Dùng biểu thức/query được chính thức hỗ trợ, không thay bằng regex trên ciphertext.

### Bài 26. Cần full-text search trên ghi chú sức khỏe

MedicalNote chứa đoạn dài hàng nghìn ký tự. Yêu cầu tìm mọi tài liệu chứa bất kỳ từ khóa hoặc câu gần nghĩa.

**Câu hỏi:** Có nên bật QE substring rồi coi nó là full-text/semantic search?

**Đáp án:** Không. QE substring trên phiên bản hỗ trợ áp dụng cho các String/query length có giới hạn, không phải Atlas Search/Vector Search đầy đủ trên ghi chú dài. Phải đánh giá kiến trúc tìm kiếm trong ranh giới quyền riêng tư hoặc thay yêu cầu.

### Bài 27. KMS outage

Key provider mất kết nối, một service đề xuất ghi tạm salary plaintext để không gián đoạn.

**Câu hỏi:** Có nên làm vậy không?

**Đáp án:** Không nếu policy yêu cầu field encryption. Hệ thống cần fail closed, retry/queue có giới hạn, cảnh báo và kế hoạch khôi phục; không được âm thầm hạ mức bảo vệ.

### Bài 28. Migration có dữ liệu cũ plaintext

Collection có 1 triệu records plaintext. Team bật encryptedFieldsMap trong service rồi ghi records mới bằng QE.

**Câu hỏi:** Vì sao search và bảo mật có thể sai?

**Đáp án:** Records cũ chưa được mã hóa nên encrypted query có thể không match; plaintext vẫn tồn tại trong collection/backups. Cần migration tạo collection đích, backfill/re-encrypt, đối soát và cutover.

### Bài 29. Thiết kế hệ thống hồ sơ nhân sự

Yêu cầu:

~~~text
employeeCode: tìm chính xác và unique theo tenant
departmentId: lọc, group
createdAt: lọc/sort
taxId: tìm equality, không được lộ
salary: lọc theo khoảng, không được lộ
medicalNote: chỉ đọc sau khi tìm đúng người
~~~

**Bài làm:** Lập bảng field:

1. Field nào để plaintext theo threat model?
2. Field nào CSFLE randomized/QE none?
3. Field nào QE equality?
4. Field nào QE range?
5. Index thường nào được phép?
6. Cách bảo đảm unique employeeCode và tenant isolation?
7. Có cần thay đổi cách làm báo cáo trung bình salary không?

**Một đáp án phù hợp:** tenantId/employeeCode/departmentId/createdAt có thể để dạng metadata nếu policy cho phép, dùng index thường. taxId QE equality, salary QE range, medicalNote queryType none hoặc randomized CSFLE tùy collection architecture. Không dùng salary ciphertext để sort/avg; unique employeeCode dùng nguyên tắc uniqueness trên field không mã hóa và theo topology. Phải kiểm tra toàn bộ workflow quyền và version.

### Bài 30. Chọn phương án cho API tìm khách hàng

Ứng dụng cần tìm khách hàng bằng:

- Exact customerRef.
- Exact encrypted taxId.
- Một phần chuỗi encrypted phone.
- Ghi chú tự do dài vài trang.

**Câu hỏi:** Có một index loại duy nhất giải quyết cả bốn không?

**Đáp án:** Không. customerRef dùng index exact thông thường; taxId dùng QE equality hoặc CSFLE deterministic trong các điều kiện phù hợp; phone partial String search cần QE String query và phiên bản hỗ trợ, hoặc thay thiết kế; ghi chú dài đòi đánh giá mô hình search riêng và bảo mật. Không xem một B-tree index hay một encrypted queryType là giải pháp universal.

### Bài 31. Review một thiết kế có metadata tiết lộ bí mật

Document:

~~~javascript
{
  salary: BinData(/* encrypted */),
  salaryForSort: 95000,
  salaryBand: "TOP_1_PERCENT"
}
~~~

**Câu hỏi:** Những field phụ có thể phá vỡ mục tiêu gì?

**Định hướng:** salaryForSort lộ salary trực tiếp; salaryBand có thể tiết lộ thông tin nhạy cảm qua phân loại. Threat model phải xem mọi metadata và dẫn xuất, không chỉ field được gắn nhãn encrypted.

### Bài 32. Xây ma trận compatibility

Giả sử tổ chức dùng MongoDB 8.0 ở production và MongoDB 9.0 ở lab.

**Yêu cầu:** Lập ma trận cho:

1. CSFLE deterministic equality.
2. CSFLE randomized query theo giá trị.
3. QE equality.
4. QE range.
5. QE prefix/suffix/substring.
6. QE unique constraint plaintext.
7. QE encrypted shard key.
8. QE aggregation sum/sort trên salary.

**Định hướng:** Chỉ đánh dấu Supported sau khi có bằng chứng từ tài liệu đúng version/driver. Không lấy tính năng String 9.0 để điền Supported cho 8.0; không đánh dấu unique/plaintext sort chỉ vì query range chạy được.

## 33. Checklist trước khi triển khai encrypted field

### 33.1. Thiết kế dữ liệu

- [ ] Có threat model và danh sách field phải được bảo vệ.
- [ ] Có danh sách **những query bắt buộc** theo field.
- [ ] Với mỗi field đã chọn **CSFLE deterministic/randomized** hoặc **QE queryType** hợp lệ.
- [ ] Đã xác nhận BSON type, optional/null behavior và nested/array limitations.
- [ ] Đã đánh giá metadata plaintext có tiết lộ thông tin nhạy cảm không.
- [ ] Đã chọn shard key không mã hóa nếu dùng sharding.
- [ ] Đã có phương án uniqueness, không dựa vào QE ciphertext unique index.

### 33.2. Server, driver và keys

- [ ] Server/FCV/driver/crypt library hỗ trợ tính năng dự kiến.
- [ ] Có key vault, KMS credentials và phân quyền riêng.
- [ ] Encryption schema và queryType được version hóa.
- [ ] Có server-side enforcement phù hợp để tránh plaintext writes ngoài ý muốn.
- [ ] Không có secret/key material trong repository, log hoặc tài liệu công khai.
- [ ] Có phương án KMS outage và key rotation.

### 33.3. Index và truy vấn

- [ ] QE collection/index được tạo đúng quy trình.
- [ ] Không tự thêm B-tree index vào QE encrypted field để thay encrypted index.
- [ ] Các query equality/range/string chỉ sử dụng operator được hỗ trợ.
- [ ] Không dùng sort, sum, avg, regex, full-text trên ciphertext như plaintext.
- [ ] Các thao tác update/upsert/bulk phù hợp danh sách supported operations.
- [ ] Những báo cáo và joins có thiết kế thích hợp với encrypted fields.

### 33.4. An toàn và vận hành

- [ ] API kiểm quyền field-level trước khi trả nội dung đã giải mã.
- [ ] TenantId và các quyền được lấy từ authentication, không tin input tự khai.
- [ ] Có telemetry cho encryption errors, KMS latency, metadata growth và migration.
- [ ] Logs/traces không xuất plaintext nhạy cảm hoặc keys.
- [ ] Có backup/restore test với quyền giải mã phù hợp.
- [ ] Có kế hoạch migration plaintext/CSFLE cũ và xử lý dữ liệu lịch sử.
- [ ] Đã chạy thử trên dataset không chứa bí mật thật trước khi rollout.

## 34. Nguồn tham khảo theo phiên bản

Những giới hạn trong bài thay đổi theo MongoDB server/driver. Nên chọn đúng nhánh phiên bản trước khi dùng ví dụ trên production. Nguồn chính thức:

- [MongoDB — Choose an In-Use Encryption Approach](https://www.mongodb.com/docs/manual/core/queryable-encryption/about-qe-csfle/)
- [MongoDB — CSFLE Encryption Algorithms](https://www.mongodb.com/docs/manual/core/csfle/fundamentals/encryption-algorithms/)
- [MongoDB — CSFLE Supported Operations](https://www.mongodb.com/docs/manual/core/csfle/reference/supported-operations/)
- [MongoDB — CSFLE Limitations](https://www.mongodb.com/docs/manual/core/csfle/reference/limitations/)
- [MongoDB — QE Supported Operations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/supported-operations/)
- [MongoDB — QE Limitations](https://www.mongodb.com/docs/manual/core/queryable-encryption/reference/limitations/)
- [MongoDB — QE Create an Encryption Schema](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-create-encryption-schema/)
- [MongoDB — QE Encrypted Fields and Enabled Queries](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/encrypt-and-query/)
- [MongoDB — Estimate QE Storage Impact](https://www.mongodb.com/docs/manual/core/queryable-encryption/qe-estimate-storage-impact/)
- [MongoDB — Queryable Encryption Explicit Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/fundamentals/manual-encryption/)
- [MongoDB — MongoDB 8.2 Release Notes](https://www.mongodb.com/docs/manual/release-notes/8.2/)
- [MongoDB — QE Prefix, Suffix, Substring GA Announcement (29/09/2026)](https://www.mongodb.com/products/updates/now-ga-queryable-encryption-prefix-suffix-and-substring-support/)

Các trang **/manual/** thường theo phiên bản tài liệu hiện hành. Nếu dùng server cũ hơn, hãy mở đúng đường dẫn tài liệu dành cho version tương ứng, ví dụ **/v8.0/** hoặc **/v7.0/**, và đối chiếu driver documentation.

## 35. Kết luận

Client-side field encryption bảo vệ dữ liệu trước khi nó đi vào MongoDB, nhưng đổi lại ứng dụng **không thể giả định mọi tính năng truy vấn và index của plaintext vẫn hoạt động**. Cần nhớ sự khác biệt:

~~~text
                 FIELD ENCRYPTION
                       |
          +------------+-------------+
          |                          |
         CSFLE                 QUERYABLE ENCRYPTION
          |                          |
    +-----+------+          +--------+---------+
    |            |          |        |         |
Deterministic Randomized  Equality  Range  String query
    |            |          |        |         |
  Exact       No direct    Exact    Range   Prefix / suffix /
 equality    value query  lookup   filters  substring by version
    |            |          |        |         |
    +------------+----------+--------+---------+
                       |
                       v
           INDEX, SCHEMA, KEYS, VERSION
                       |
                       v
            APP AUTHORIZATION + AUDIT
~~~

**Mười nguyên tắc quan trọng:**

1. **MongoDB chỉ thấy ciphertext** của field được client-side encrypt đúng; một phép tính hoặc so sánh BSON trên ciphertext không tự có nghĩa plaintext.
2. **CSFLE deterministic** có thể hỗ trợ equality nhưng tiết lộ pattern trùng giá trị; **randomized** bảo vệ sự lặp tốt hơn nhưng không tìm trực tiếp theo nội dung.
3. **Queryable Encryption** cho phép những loại query được định nghĩa trước như equality, range và String prefix/suffix/substring theo phiên bản hỗ trợ; nó **không biến mọi operator thành hợp lệ**.
4. **Không thêm B-tree index lên QE encrypted field** để thay QE index. Query metadata và **__safeContent__** phải được quản lý theo thiết kế hỗ trợ.
5. **Unique index trên randomized/QE ciphertext không bảo đảm plaintext uniqueness**. Uniqueness cần một mô hình business/concurrency an toàn riêng.
6. **Encrypted shard key, arrays, null, collation, sort, aggregation, joins, update/bulk, views, time series và Search** đều có các giới hạn cần đánh giá trước khi chọn schema.
7. **Range query không đồng nghĩa sort/avg/sum plaintext**. Muốn phép tính khác queryType cần xử lý ở tầng được ủy quyền hoặc đổi kiến trúc.
8. **Mọi query cần đúng client, key, BSON type, queryType và version**. Một client MongoDB thông thường không tự giải mã chỉ vì biết URI.
9. **Key management và authorization là hai trách nhiệm khác nhau**: quyền decrypt của backend không phải quyền xem của từng user; metadata dẫn xuất/log cũng có thể làm lộ thông tin.
10. **Mã hóa trường là quyết định kiến trúc và lifecycle**. Migration, rotation, encrypted query index, compaction, backups và version compatibility cần runbook, không chỉ một tham số.

Lời giải tốt thường bắt đầu từ **“người dùng thực sự phải truy vấn gì?”** và **“server được phép biết những metadata nào?”**. Khi hai câu hỏi này được trả lời rõ ràng, mới nên chọn CSFLE hay Queryable Encryption, chọn queryType, thiết kế index/khóa, và xác nhận các tính năng MongoDB cần thiết vẫn được hỗ trợ. Mục tiêu không phải chỉ là bật mã hóa thành công, mà là **bảo vệ dữ liệu mà vẫn thực hiện đúng các truy vấn nghiệp vụ được cho phép, với những giới hạn được hiểu và kiểm chứng rõ ràng**.
