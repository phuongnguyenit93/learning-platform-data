# Index mặc định _id và quản lý createIndex, getIndexes, dropIndex trong MongoDB

## 1. Tại sao cần index trong MongoDB?

Một collection MongoDB có thể chứa hàng triệu document BSON. Giả sử ứng dụng có collection **customers** và phải tìm khách hàng theo mã:

~~~javascript
db.customers.findOne({ _id: ObjectId("64b000000000000000000001") });
~~~

Nếu không có một cấu trúc truy cập phù hợp, database có thể phải duyệt nhiều document để tìm một bản ghi. **Index** cung cấp cấu trúc dữ liệu được tổ chức theo các khóa tìm kiếm để MongoDB có thể xác định document phù hợp hiệu quả hơn.

Trong MongoDB, các index thông thường dựa trên cấu trúc tương tự **B-tree**. Mỗi index duy trì các khóa được suy ra từ một hoặc nhiều field của document và tham chiếu đến document liên quan. Query planner có thể sử dụng index để tìm dữ liệu, sắp xếp hoặc hỗ trợ một số truy vấn chỉ cần dữ liệu đã có trong index.

Tuy nhiên, index không miễn phí:

- Tốn **dung lượng lưu trữ** và có thể chiếm bộ nhớ cache.
- Mỗi **insert/update/delete** có liên quan phải duy trì dữ liệu index.
- Tạo index trên collection lớn tiêu tốn thời gian và tài nguyên.
- Một index không đúng truy vấn có thể không được dùng, dù vẫn làm tăng chi phí ghi.

MongoDB tự tạo một index đặc biệt trên trường **_id** cho collection thông thường. Các index khác do người phát triển hoặc người vận hành lựa chọn theo cách ứng dụng truy cập dữ liệu.

### 1.1. Ba thao tác quản lý index cơ bản

| Lệnh | Câu hỏi trả lời | Tác dụng |
|---|---|---|
| **createIndex()** | Muốn tạo index trên những field nào và với tùy chọn nào? | Tạo một index nếu hợp lệ và chưa có định nghĩa tương đương. |
| **getIndexes()** | Collection hiện đang có những index nào? | Liệt kê các thông số index đã được tạo. |
| **dropIndex()** | Muốn loại bỏ một index không còn cần dùng? | Gỡ index được chỉ định, trừ các index được MongoDB bảo vệ như **_id_**. |

Đây là vòng đời cơ bản:

~~~text
               Collection MongoDB
                       |
            Index _id mặc định
                       |
               Đo access patterns
                       |
               createIndex(...)
                       |
               getIndexes(...)
                       |
              explain(...) + đo tải
                       |
          +------------+-------------+
          |                          |
      Index hữu ích             Index dư thừa
          |                          |
       Giữ lại             Xem xét hide/thử nghiệm
                                     |
                                dropIndex(...)
~~~

## 2. Index mặc định trên _id

### 2.1. _id là danh tính của document

Mỗi document trong collection thông thường đều có trường **_id** dùng làm định danh. Ví dụ:

~~~javascript
{
  _id: ObjectId("64b000000000000000000001"),
  customerCode: "CUST-001",
  fullName: "Nguyen Van A",
  status: "ACTIVE"
}
~~~

MongoDB tạo **unique index** trên **_id** khi tạo collection thông thường:

~~~javascript
{
  key: { _id: 1 },
  name: "_id_",
  unique: true
}
~~~

Đây là biểu diễn rút gọn một phần index specification. Kết quả thật từ **getIndexes()** có thể còn trường **v** và những metadata khác tùy phiên bản MongoDB.

Các thuộc tính quan trọng:

1. **Mặc định có sẵn:** không cần gọi **createIndex({ _id: 1 })** để tối ưu truy vấn theo **_id** trên collection thông thường.
2. **Unique:** không cho phép hai document trong cùng phạm vi uniqueness được kiểm soát có cùng giá trị **_id**.
3. **Bắt buộc:** trong collection thông thường, không thể xóa index **_id_**.
4. **_id gần như bất biến:** ứng dụng không thể đổi giá trị **_id** của document đã lưu bằng một update thông thường.
5. **Có thể dùng kiểu BSON khác ObjectId:** **_id** không bắt buộc phải là ObjectId, miễn giá trị hợp lệ và đáp ứng quy tắc MongoDB.

**Điểm cần thận trọng:** đối với **sharded collection**, index **_id** có những giới hạn riêng về tính duy nhất trên toàn cluster khi **_id** không phải shard key. Bài sẽ làm rõ ở phần sau; không nên khẳng định unique _id luôn được cưỡng chế toàn cluster trong mọi cấu hình sharding.

### 2.2. MongoDB tự tạo _id khi ứng dụng không cung cấp

Trong **mongosh**:

~~~javascript
use index_basics_lab

db.customers.insertOne({
  customerCode: "CUST-001",
  fullName: "Nguyen Van A",
  status: "ACTIVE"
});
~~~

Nếu không truyền **_id**, MongoDB driver/mongosh thường tạo giá trị **ObjectId** cho document trước khi gửi đi hoặc trong quá trình xử lý insert tương ứng. Kết quả có thể có:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("...")
}
~~~

**ObjectId** là kiểu BSON thường dùng để tạo định danh với xác suất trùng rất thấp. Nó không phải công cụ bảo đảm ID không bao giờ trùng theo nghĩa toán học và cũng không phải hợp đồng thay thế business key cho mọi miền nghiệp vụ. **Unique index trên _id** mới là cơ chế từ chối trùng tại database theo phạm vi được hỗ trợ.

### 2.3. Có thể dùng _id dạng string hoặc số?

Có thể định nghĩa ID do ứng dụng cấp:

~~~javascript
db.customers.insertOne({
  _id: "CUS-HN-001",
  customerCode: "CUST-002",
  fullName: "Tran Thi B",
  status: "ACTIVE"
});
~~~

MongoDB lưu **_id** như BSON string trong trường hợp này. Một số lựa chọn hợp lệ khác gồm số nguyên và những kiểu BSON được hỗ trợ, với các ràng buộc riêng của field _id. Trong hệ thống thực tế, nên **thống nhất một kiểu _id cho collection** để tránh mapper Java, API và query phải xử lý nhiều kiểu khác nhau.

Ví dụ hai truy vấn sau **không cùng nghĩa**:

~~~javascript
db.customers.findOne({
  _id: ObjectId("64b000000000000000000001")
});

db.customers.findOne({
  _id: "64b000000000000000000001"
});
~~~

Giá trị ObjectId và string chứa cùng 24 ký tự hex không phải cùng BSON type. Ứng dụng cần chuyển đổi rõ ràng khi mapping request tới query.

### 2.4. Không thay đổi _id bằng $set

~~~javascript
// Không hợp lệ nếu nhằm đổi _id của document hiện có.
db.customers.updateOne(
  { _id: "CUS-HN-001" },
  { $set: { _id: "CUS-HN-002" } }
);
~~~

MongoDB không cho phép cập nhật trực tiếp **_id** của document đã tồn tại theo cách này. Nếu nghiệp vụ cần thay đổi định danh, phải thiết kế một workflow phù hợp (ví dụ tạo document mới, cập nhật tham chiếu và xử lý document cũ), cẩn thận với consistency và unique constraints.

Với mã nghiệp vụ có thể đổi, nên cân nhắc giữ **_id** ổn định và lưu mã đó ở field riêng như **customerCode**, đồng thời tạo unique index nếu mã nghiệp vụ phải duy nhất.

### 2.5. Tại sao không thể xóa index _id_?

Index mặc định **_id_** gắn với cơ chế định danh của collection thông thường. Thử:

~~~javascript
db.customers.dropIndex("_id_");
~~~

MongoDB từ chối yêu cầu. Không nên sử dụng phương pháp ngoài tài liệu để sửa file index trên đĩa, vì có thể làm hỏng dữ liệu.

**Ngoại lệ mô hình lưu trữ:** một số dạng collection đặc biệt, chẳng hạn **clustered collections**, có cách tổ chức khóa cluster và metadata khác collection thông thường. Khi kiểm tra hệ thống cụ thể, nên dựa vào loại collection và kết quả catalog thực tế thay vì áp dụng mọi quy tắc index vật lý cho tất cả loại collection.

## 3. Tạo và xem index mặc định trong mongosh

### 3.1. Tạo collection thử nghiệm

~~~javascript
use index_basics_lab

db.createCollection("products");
~~~

Nếu collection đã tồn tại, lệnh **createCollection** báo lỗi. Dùng tên collection riêng cho lab hoặc bỏ bước này nếu đã tạo.

Xem các index:

~~~javascript
db.products.getIndexes();
~~~

Kết quả điển hình:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  }
]
~~~

Một số trường metadata có thể thay đổi theo phiên bản; không hardcode điều kiện phải có chính xác toàn bộ các key trên. Dù **unique: true** không nhất thiết được in tường minh trong mọi bản thông số **_id_**, index mặc định vẫn mang ràng buộc uniqueness trong phạm vi được MongoDB quy định.

### 3.2. Thêm document và truy vấn theo _id

~~~javascript
db.products.insertMany([
  {
    _id: "SKU-KB-01",
    name: "Mechanical Keyboard",
    category: "ACCESSORIES",
    price: NumberDecimal("1250000.00"),
    status: "ACTIVE"
  },
  {
    _id: "SKU-MOUSE-01",
    name: "Wireless Mouse",
    category: "ACCESSORIES",
    price: NumberDecimal("350000.00"),
    status: "ACTIVE"
  },
  {
    _id: "SKU-MON-01",
    name: "27-inch Monitor",
    category: "DISPLAYS",
    price: NumberDecimal("4200000.00"),
    status: "ACTIVE"
  }
]);
~~~

Tìm theo ID:

~~~javascript
db.products.findOne({ _id: "SKU-KB-01" });
~~~

Tìm theo trường khác:

~~~javascript
db.products.find({ category: "ACCESSORIES" });
~~~

Truy vấn đầu **có thể tận dụng _id index**. Truy vấn thứ hai **không thể dùng _id index để lọc hiệu quả theo category chỉ vì index _id tồn tại**. Muốn tối ưu trường category phải xem xét index riêng theo query shape.

### 3.3. Kiểm tra trùng _id

~~~javascript
db.products.insertOne({
  _id: "SKU-KB-01",
  name: "Keyboard Duplicate"
});
~~~

Lệnh sẽ gặp lỗi **duplicate key**, thường có mã **E11000** trong thông điệp. MongoDB không âm thầm ghi đè document cũ khi dùng **insertOne** với cùng **_id**.

Khi tạo API có thể bị retry do timeout hoặc lỗi mạng, thiết kế **_id/business key ổn định** và có logic xử lý trường hợp “đã tồn tại với cùng dữ liệu” khác với “xung đột định danh”. Unique index ngăn tạo thêm bản ghi trùng, nhưng không tự quyết định chính sách idempotency.

## 4. Phân biệt _id index và index do ứng dụng tạo

Giả sử cần tìm:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

Index mặc định **{_id: 1}** được xây dựng theo _id, nên không trực tiếp sắp xếp dữ liệu theo category/status. Một index mới như:

~~~javascript
db.products.createIndex({
  category: 1,
  status: 1
});
~~~

có thể phù hợp với điều kiện truy vấn trên, tùy phân bố dữ liệu và kế hoạch query.

### 4.1. Giá trị 1 và -1 trong key specification

~~~javascript
{ category: 1, createdAt: -1 }
~~~

**1** chỉ thứ tự tăng dần, **-1** chỉ thứ tự giảm dần trong index. Với **compound index**, thứ tự field và chiều sắp xếp có thể ảnh hưởng đến khả năng hỗ trợ query có sort, đặc biệt khi sort nhiều trường với nhiều hướng.

Đừng nhầm:

~~~javascript
{ category: 1, createdAt: -1 }
~~~

với:

~~~javascript
{ createdAt: -1, category: 1 }
~~~

Hai compound index khác nhau, vì thứ tự các field là một phần quan trọng của định nghĩa và cách query có thể sử dụng index.

### 4.2. Index đơn và index ghép

Index đơn:

~~~javascript
db.products.createIndex({ category: 1 });
~~~

Index ghép:

~~~javascript
db.products.createIndex({ category: 1, status: 1 });
~~~

Một compound index thường có thể hỗ trợ các query tương ứng **prefix** của nó trong những điều kiện phù hợp, ví dụ query category với index **{category:1,status:1}**. Nhưng không mặc định cùng index đó sẽ tối ưu một query **chỉ lọc status** giống như index riêng **{status:1}**.

Việc có nhiều index không tự đảm bảo tốc độ tăng. MongoDB Query Planner chọn kế hoạch theo dữ liệu, metadata và điều kiện query; nên đánh giá bằng **explain**.

## 5. createIndex(): tạo index có chủ đích

### 5.1. Cú pháp chung

~~~javascript
db.collection.createIndex(
  { field1: 1, field2: -1 },
  {
    name: "index_name",
    // các tùy chọn như unique, partialFilterExpression...
  }
);
~~~

Các đối số:

- **Key specification:** danh sách field/index key và chiều sắp xếp hoặc loại index.
- **Options:** tên index, unique, partial filter, collation và những tùy chọn được hỗ trợ khác.
- **Giá trị trả về:** thường là tên index đã tạo hoặc tên index tương đương tồn tại, nếu lệnh thành công trong mongosh.

Ví dụ:

~~~javascript
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);
~~~

Nếu thành công, shell trả về tên như:

~~~text
ix_category_status
~~~

### 5.2. Vì sao nên đặt tên index rõ ràng?

Nếu không chỉ định **name**, MongoDB tạo tên tự động từ key pattern, ví dụ **category_1_status_1**. Tên này hợp lệ và dễ nhận biết với index đơn giản.

Trong hệ thống lớn, tên có chủ đích giúp:

1. Xác định vai trò của index trong migration và tài liệu vận hành.
2. Gỡ đúng index bằng **dropIndex("ix_category_status")**.
3. Ghi log và đo usage dễ hơn.
4. Phân biệt index có key tương tự nhưng options khác nhau, trong phạm vi các cấu hình MongoDB hỗ trợ.

Một quy ước có thể là:

~~~text
ix_<field>_<field>
uq_<field>_<field>
ttl_<field>
partial_<purpose>
~~~

Đây là quy ước tên của nhóm phát triển, không phải yêu cầu cú pháp MongoDB. Nên giữ tên ổn định qua các migration để vận hành dễ kiểm soát.

### 5.3. Tạo unique index

Giả sử **productCode** phải duy nhất trong từng **tenantId**:

~~~javascript
db.products.createIndex(
  { tenantId: 1, productCode: 1 },
  {
    unique: true,
    name: "uq_tenant_product_code"
  }
);
~~~

Khi unique compound index tồn tại, hai document có cùng **tenantId** và **productCode** không thể cùng được lưu trong phạm vi MongoDB cưỡng chế uniqueness. Nhưng hai tenant khác nhau vẫn có thể dùng chung productCode.

**Unique index không tự làm sạch dữ liệu trùng.** Nếu collection đã có những tổ hợp khóa trùng, quá trình tạo unique index có thể thất bại. Cần xác định và xử lý các bản ghi trùng trước khi xây dựng constraint.

Ví dụ tìm tổ hợp trùng để khảo sát:

~~~javascript
db.products.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        productCode: "$productCode"
      },
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

Với collection lớn, việc gom toàn bộ IDs vào array có thể vượt giới hạn kích thước aggregation document. Khi chỉ cần biết nhóm trùng, có thể bỏ **ids** và dùng quy trình báo cáo theo batch. Đây là ví dụ dành cho dữ liệu thử nghiệm, không phải lệnh tối ưu cho mọi production workload.

### 5.4. Tạo unique index không đồng nghĩa bắt buộc mọi field có dữ liệu

Đối với unique index thông thường, các document thiếu field hoặc có **null** có thể tạo ra index entry tương ứng với null/missing theo quy tắc MongoDB, dẫn tới duplicate key ở một số trường hợp. Với unique index đơn trên field tùy chọn, có thể chỉ cho phép một document có giá trị khóa null/missing theo những quy tắc tương ứng.

Nếu chỉ yêu cầu uniqueness cho những document **có một field nhất định**, cần thiết kế **partial unique index**, schema validation hoặc quy tắc khác phù hợp. Không nên cứ đặt **unique: true** rồi giả định các document thiếu field đều được bỏ qua.

### 5.5. Tạo partial index

Giả sử chỉ thường xuyên truy vấn các sản phẩm **ACTIVE**:

~~~javascript
db.products.createIndex(
  { category: 1 },
  {
    name: "ix_active_category",
    partialFilterExpression: {
      status: "ACTIVE"
    }
  }
);
~~~

Index này chỉ chứa document thỏa **status: "ACTIVE"**. Query phù hợp:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

Query planner chỉ có thể sử dụng partial index khi điều kiện truy vấn bảo đảm không làm thiếu kết quả so với predicate đã định nghĩa. Một query chỉ lọc category nhưng không giới hạn status có thể **không dùng partial index** này vì nó không chứa dữ liệu của các document khác trạng thái ACTIVE.

### 5.6. Tạo TTL index

Với collection dữ liệu có thời hạn sống như token hết hạn, có thể dùng **TTL index**:

~~~javascript
db.temporary_sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_expires_at",
    expireAfterSeconds: 0
  }
);
~~~

**expiresAt** phải mang kiểu BSON Date phù hợp. TTL monitor của MongoDB dọn dữ liệu hết hạn một cách **bất đồng bộ**; không có cam kết rằng document biến mất đúng mili giây khi expiresAt tới hạn. TTL cần được chọn có chủ ý vì nó xóa dữ liệu, khác với index chỉ hỗ trợ query.

### 5.7. Index có collation

Nếu ứng dụng cần so sánh tên không phân biệt chữ hoa/chữ thường theo locale phù hợp, có thể cân nhắc collation:

~~~javascript
db.customers.createIndex(
  { fullName: 1 },
  {
    name: "ix_customer_name_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Để hưởng lợi từ index có collation, query cần có collation tương thích với index hoặc collection default tương ứng:

~~~javascript
db.customers.find({
  fullName: "nguyen van a"
}).collation({
  locale: "en",
  strength: 2
});
~~~

**Collation** ảnh hưởng semantics so sánh string, index usage và uniqueness. Không nên thay collation khi chưa xác nhận quy tắc ngôn ngữ/đối chiếu của dữ liệu nghiệp vụ.

### 5.8. createIndexes() để khai báo nhiều index

MongoDB còn có **createIndexes()**, cho phép khai báo nhiều index trong một lời gọi:

~~~javascript
db.products.createIndexes([
  {
    key: { category: 1, status: 1 },
    name: "ix_category_status"
  },
  {
    key: { price: 1 },
    name: "ix_price"
  }
]);
~~~

Không nên hiểu việc tạo nhiều index trong một command đồng nghĩa toàn bộ việc xây dựng các index được giao dịch hóa và rollback như một transaction ứng dụng. Việc sử dụng cụ thể tùy phiên bản, khối lượng dữ liệu và quy trình vận hành.

## 6. Nếu gọi createIndex() lặp lại thì sao?

MongoDB có cơ chế kiểm tra index đang tồn tại. Khi một lời gọi **createIndex** có định nghĩa trùng với index có sẵn theo quy tắc tương đương của phiên bản server, MongoDB thường **không xây dựng một bản sao mới**.

~~~javascript
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);

db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);
~~~

Lời gọi thứ hai thông thường không tạo thêm một index có cùng tên và cùng định nghĩa.

Tuy nhiên cần phân biệt:

- **Cùng key pattern nhưng đổi options:** một số options không thể sửa bằng cách gọi lại createIndex; có thể bị conflict hoặc cần thao tác **collMod** hay drop/recreate tùy option.
- **Cùng tên nhưng khác key pattern:** có thể bị từ chối vì tên đã gắn với định nghĩa khác.
- **Cùng key pattern, collation/partialFilterExpression khác:** khả năng tồn tại song song và quy tắc tương đương có ràng buộc riêng theo phiên bản; không tự đoán.
- **Thêm unique: true cho index cũ không unique:** không thể giả định gọi createIndex cùng key với option mới sẽ biến index cũ thành unique.

**Định nghĩa index là schema vận hành**, nên cần kiểm tra specification thực tế trước khi kết luận một lần “ensure index” đã đạt yêu cầu.

### 6.1. Bảo vệ việc triển khai migration

Trong ứng dụng có nhiều instance cùng khởi động, không nên để mọi instance tự phát một loạt lệnh tạo/xóa index lớn mà không có điều phối. Có thể chọn:

1. Quản lý index qua migration/deployment job có version.
2. Chỉ chạy migration từ một owner được điều phối.
3. Kiểm tra **getIndexes** trước và sau thay đổi.
4. Xem log thời gian build, CPU/I/O và tác động tới query latency.
5. Có kế hoạch rollback dựa vào index name và hiệu năng.

Gọi lại createIndex cùng spec thường là an toàn hơn so với drop/recreate, nhưng vẫn cần kiểm soát concurrency, thời gian build và lỗi options không tương thích.

## 7. getIndexes(): kiểm tra catalog index

### 7.1. Liệt kê index của một collection

~~~javascript
db.products.getIndexes();
~~~

Kết quả minh họa sau khi tạo một số index:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  },
  {
    v: 2,
    key: { category: 1, status: 1 },
    name: "ix_category_status"
  },
  {
    v: 2,
    key: { tenantId: 1, productCode: 1 },
    name: "uq_tenant_product_code",
    unique: true
  }
]
~~~

Đây là ví dụ rút gọn, không nhất thiết trùng mọi field/version trong môi trường thật. Tùy index, catalog có thể có:

| Trường | Ý nghĩa thường gặp |
|---|---|
| **name** | Tên định danh index, dùng để drop/hide hoặc theo dõi. |
| **key** | Key pattern; thứ tự field và chiều/index type. |
| **unique** | Có quy tắc uniqueness (với index thường; metadata _id có cách biểu diễn riêng). |
| **partialFilterExpression** | Predicate giới hạn tập document được index. |
| **sparse** | Tùy chọn index chỉ lưu entry cho những document phù hợp quy tắc sparse. |
| **expireAfterSeconds** | TTL duration cho index TTL phù hợp. |
| **collation** | Quy tắc so sánh string của index. |
| **hidden** | Index được ẩn khỏi query planner khi cấu hình hỗ trợ. |
| **v** | Version định dạng index nội bộ, không phải phiên bản migration của ứng dụng. |

**getIndexes() liệt kê index specification, không phải báo cáo số lần index được sử dụng, kích thước từng index hay chi phí query.** Muốn khảo sát hiệu năng cần thêm **explain**, **$indexStats**, **stats** và hệ giám sát phù hợp.

### 7.2. Xem tên các index

~~~javascript
db.products.getIndexes().map(index => index.name);
~~~

Kết quả ví dụ:

~~~javascript
[
  "_id_",
  "ix_category_status",
  "uq_tenant_product_code"
]
~~~

Đoạn mã này hữu ích cho thao tác quản trị nhưng không nên dùng để tự động chọn index cần xóa chỉ dựa trên tên giống một chuỗi con.

### 7.3. Kiểm tra một index đã có hay chưa

~~~javascript
const indexes = db.products.getIndexes();
const index = indexes.find(
  spec => spec.name === "ix_category_status"
);

if (index) {
  printjson(index);
} else {
  print("Index chưa tồn tại");
}
~~~

Việc xác nhận tên chỉ là bước đầu. Nếu cần đảm bảo định nghĩa chính xác, kiểm tra thêm **key**, **unique**, **partialFilterExpression**, **collation** và các options quan trọng khác; đừng kết luận chỉ vì tên trùng.

### 7.4. Liệt kê index bằng listIndexes command

Ngoài helper của mongosh, MongoDB có **listIndexes** command:

~~~javascript
db.runCommand({
  listIndexes: "products"
});
~~~

Command trả về cursor các index specification, hữu ích trong các công cụ quản trị/driver. Khi dùng lệnh ở cấp command phải xử lý cursor theo quy tắc MongoDB, thay vì giả định response lúc nào cũng là một mảng hoàn chỉnh giống **getIndexes()**.

### 7.5. getIndexes() và $indexStats khác nhau

**getIndexes()** trả về **định nghĩa**. **$indexStats** trả về số liệu thống kê mức truy cập index, ví dụ:

~~~javascript
db.products.aggregate([
  { $indexStats: {} }
]);
~~~

Kết quả có thể bao gồm tên index, host, thời gian tính thống kê và các bộ đếm truy cập kể từ một mốc quan sát. Thống kê truy cập có thể bị reset sau sự kiện như restart hoặc thay đổi index; chúng không tự chứng minh một index không cần thiết.

Một index có số lượt truy cập thấp vẫn có thể rất quan trọng cho:

- truy vấn báo cáo chạy hàng tháng;
- một endpoint hiếm nhưng có SLA cao;
- quy tắc **unique constraint**;
- transaction hoặc một quy trình vận hành đặc biệt.

Không xóa index chỉ vì **accesses.ops** đang thấp ở một cửa sổ quan sát ngắn.

## 8. Kiểm tra index được sử dụng bằng explain()

Tạo một truy vấn:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

Sau khi tạo index **{category:1,status:1}**, kiểm tra query plan:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
}).explain("executionStats");
~~~

Một kết quả **explain** có thể hiển thị các stage như:

- **IXSCAN:** đọc khóa từ index phù hợp.
- **FETCH:** lấy document từ collection khi cần thêm dữ liệu ngoài index hoặc thực hiện kiểm tra.
- **COLLSCAN:** duyệt document trong collection.
- **PROJECTION_COVERED** hoặc các plan stages tương ứng với engine/phiên bản: có thể liên quan đến truy vấn được index bao phủ.

Trong phiên bản mới, biểu diễn query plan có thể khác do **slot-based execution engine** và các thay đổi nội bộ. Không dựa vào một đường dẫn JSON duy nhất trong explain của mọi phiên bản.

### 8.1. Chỉ số đáng chú ý

| Chỉ số | Ý nghĩa |
|---|---|
| **nReturned** | Số document trả về. |
| **totalKeysExamined** | Số khóa index đã được đọc/xem xét. |
| **totalDocsExamined** | Số document đã được đọc/xem xét. |
| **winningPlan** | Kế hoạch query planner chọn. |
| **executionTimeMillis** | Thời gian được báo trong executionStats; cần hiểu giới hạn đo và tác động của môi trường. |

Nếu **nReturned = 10** nhưng **totalDocsExamined = 1.000.000**, truy vấn có thể đang quét quá nhiều document. Nhưng đừng mặc định index scan luôn tốt hơn collection scan: với collection nhỏ hoặc query trả về phần lớn dữ liệu, collection scan đôi khi là lựa chọn hợp lý.

### 8.2. Index _id và truy vấn theo _id

~~~javascript
db.products.find({
  _id: "SKU-KB-01"
}).explain("executionStats");
~~~

Truy vấn equality trên **_id** thường là trường hợp MongoDB có thể khai thác index mặc định rất hiệu quả. Tùy planner/engine, plan có thể xuất hiện stage đặc biệt liên quan **IDHACK/EXPRESS_IXSCAN** ở các phiên bản hỗ trợ hoặc stage index tương ứng. Điều cần quan sát là số document/key được xét và thời gian truy vấn thực tế.

### 8.3. Query covered và _id mặc định trong projection

Ví dụ index:

~~~javascript
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);
~~~

Truy vấn chỉ lấy hai field đã có trong index:

~~~javascript
db.products.find(
  {
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    _id: 0,
    category: 1,
    status: 1
  }
).explain("executionStats");
~~~

Query này **có thể** là **covered query** nếu index và query thỏa các điều kiện cần thiết, vì projection không đòi field ngoài index và đã loại **_id**.

Nếu không ghi **_id: 0**, MongoDB trả **_id** theo mặc định; trong khi index **{category:1,status:1}** không chứa _id làm key được định nghĩa. Việc phải trả _id có thể khiến query cần **FETCH**. Đây là lý do nên kiểm tra projection khi phân tích covered query.

### 8.4. Explain của một query không thay thế benchmark

**explain()** hỗ trợ hiểu kế hoạch, nhưng môi trường production còn có:

- độ trễ mạng;
- số connection đồng thời;
- dữ liệu còn trong cache hay phải đọc đĩa;
- replication/write load;
- mức phân bố tenant/shard;
- workload peak và p95/p99 latency.

Hãy kết hợp explain với metrics và benchmark trên dữ liệu đại diện, thay vì chỉ tối ưu một query đã warm cache trong môi trường nhỏ.

## 9. dropIndex(): gỡ một index cụ thể

### 9.1. Xóa theo tên

~~~javascript
db.products.dropIndex("ix_category_status");
~~~

Lệnh yêu cầu MongoDB gỡ index có **name** tương ứng nếu index tồn tại và được phép gỡ. Khi index bị gỡ, MongoDB không còn sử dụng cấu trúc đó để hỗ trợ query. Dữ liệu document **không bị xóa chỉ vì dropIndex**.

**Không nhầm dropIndex với drop():**

~~~javascript
db.products.dropIndex("ix_category_status"); // Gỡ một index

// db.products.drop();                       // Xóa collection và dữ liệu
~~~

Dòng **drop()** chỉ là nhắc nhở, không phải bước thực hành cần chạy.

### 9.2. Xóa theo key pattern

MongoDB cũng hỗ trợ chỉ định key pattern để gỡ index phù hợp:

~~~javascript
db.products.dropIndex({
  category: 1,
  status: 1
});
~~~

Trong vận hành, **tên index chính xác** thường dễ kiểm soát hơn, nhất là khi có các cấu hình index với options khác nhau. Trước khi xóa, đọc **getIndexes()** để xác nhận tên, key và options.

### 9.3. Không được xóa index _id_

~~~javascript
db.products.dropIndex("_id_");
~~~

MongoDB từ chối thao tác trên index bắt buộc. Không tìm cách vòng qua bằng cách sửa tệp dữ liệu trực tiếp.

### 9.4. Drop một index tác động đến query

Giả sử có một endpoint:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

Khi gỡ **ix_category_status**, query planner phải tìm kế hoạch khác: có thể dùng một index thay thế, kết hợp các lựa chọn khác hoặc collection scan. Trong collection lớn, latency có thể tăng mạnh.

**Drop index là thay đổi khả năng phục vụ query**, không chỉ thu hồi dung lượng. Cần xác định trước:

- endpoint nào phụ thuộc vào index;
- query nào đang dùng index;
- index khác có hỗ trợ đủ điều kiện/sort hay không;
- quy trình khôi phục nếu hiệu năng giảm;
- thời điểm triển khai và mức tải của database.

### 9.5. Không dùng dropIndexes("*") tùy tiện

MongoDB có helper **dropIndexes()** và có cách chỉ định xóa nhiều index, tùy API. Ví dụ:

~~~javascript
// Chỉ dùng trong collection LAB nếu chủ động muốn xóa mọi
// index có thể xóa, ngoại trừ index _id_ được bảo vệ.
// db.products.dropIndexes();
~~~

Đây là thao tác rộng, không nên dùng trong migration production nếu chỉ cần xóa một index cụ thể. Nó có thể khiến hàng loạt query trở nên chậm và các unique constraints do index phụ trách không còn được cưỡng chế.

### 9.6. Khi xóa unique index thì sao?

Nếu một unique index như:

~~~javascript
db.products.createIndex(
  { tenantId: 1, productCode: 1 },
  {
    name: "uq_tenant_product_code",
    unique: true
  }
);
~~~

bị xóa:

~~~javascript
db.products.dropIndex("uq_tenant_product_code");
~~~

thì ràng buộc uniqueness của **tenantId + productCode** do index đó thực thi cũng không còn. Sau đó, hai document với cùng tổ hợp khóa có thể được ghi vào collection nếu không có constraint khác ngăn lại.

Do đó một index **unique** vừa là cấu trúc tối ưu truy vấn, vừa là **bất biến dữ liệu**. Không được đánh giá việc xóa nó chỉ bằng access metrics; cần xác nhận domain và các hệ thống phụ thuộc.

## 10. Hide index: thử ảnh hưởng trước khi drop

MongoDB hỗ trợ **hidden indexes** trong các phiên bản phù hợp. Khi một index bị ẩn:

- Query planner **không chọn** index đó để lập kế hoạch query bình thường.
- Index vẫn tồn tại và tiếp tục được bảo trì khi document được ghi.
- Có thể **unhide** mà không phải xây dựng lại toàn bộ index, giúp thử nghiệm tác động của việc không dùng index.

Ví dụ với một index thường **không phải _id_**:

~~~javascript
db.products.hideIndex("ix_category_status");
~~~

Sau đó:

~~~javascript
db.products.getIndexes();
~~~

Index được ẩn có thể có **hidden: true** trong specification. Kiểm tra kế hoạch query:

~~~javascript
db.products.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
}).explain("executionStats");
~~~

Nếu phát hiện suy giảm không chấp nhận được:

~~~javascript
db.products.unhideIndex("ix_category_status");
~~~

Nếu đã quan sát đủ, xác định index không còn cần thiết và được phép gỡ, mới thực hiện:

~~~javascript
db.products.dropIndex("ix_category_status");
~~~

**Phân biệt hide và drop:**

| | Hide index | Drop index |
|---|---|---|
| Query planner | Không dùng index bị ẩn. | Không còn index để dùng. |
| Cấu trúc index trên đĩa | Vẫn tồn tại. | Bị loại bỏ. |
| Chi phí duy trì khi ghi | Vẫn còn. | Được loại bỏ sau khi drop. |
| Khôi phục khả năng dùng index | **unhideIndex** tương đối nhanh. | Phải **createIndex** lại, tốn thời gian build. |
| Tình huống | Thử tác động của việc không có index. | Quyết định gỡ bỏ thực tế. |

Không thể dùng hidden index để “tắt” việc cưỡng chế unique constraint: một **hidden unique index** vẫn duy trì tính unique. Index mặc định **_id_** cũng không thể ẩn như các index có thể hide khác.

## 11. Quản lý index có ảnh hưởng đến ghi và tài nguyên

### 11.1. Index tăng tốc đọc nhưng tăng chi phí ghi

Giả sử mỗi lần insert một product, hệ thống phải cập nhật:

~~~text
Collection document
    |
    +-- _id_ index
    +-- ix_category_status
    +-- ix_price
    +-- uq_tenant_product_code
    +-- ...
~~~

Mỗi index bổ sung có thể khiến thao tác ghi cần duy trì thêm index keys. Với workload ghi lớn, việc tạo quá nhiều index có thể tăng I/O, áp lực cache và độ trễ write concern.

Không nên dùng quy tắc “mỗi field đều cần một index”. Chỉ tạo index từ **query patterns, sort, join/lookup, uniqueness hoặc TTL** được đo/định nghĩa rõ.

### 11.2. Tạo index trên collection lớn là công việc vận hành

Trên collection có hàng trăm triệu document, xây dựng index có thể:

- Phải đọc lượng lớn dữ liệu nguồn;
- Sử dụng CPU, RAM, I/O và dung lượng đĩa tạm thời;
- Tạo áp lực lên replication và các thành viên replica set;
- Ảnh hưởng latency của những workload đang chạy;
- Kéo dài đáng kể thời gian triển khai.

Cơ chế index build, quorum và khả năng đọc/ghi trong lúc build thay đổi theo phiên bản/topology MongoDB. Không làm theo hướng dẫn cũ về **background: true** mà không kiểm tra phiên bản: ở các bản MongoDB hiện đại, index build đã dùng cơ chế tối ưu riêng và tùy chọn **background** không còn ý nghĩa như trước.

Nên đặt index migration trong kế hoạch deployment, giám sát tiến độ và dự trù disk/CPU/network. Với Atlas, thao tác có thể được quản lý qua công cụ/phương thức được dịch vụ hỗ trợ; vẫn cần cân nhắc tải và chi phí.

### 11.3. Index không phải replacement cho schema tốt

Nếu ứng dụng query:

~~~javascript
db.products.find({
  price: "1250000.00"
});
~~~

trong khi giá được lưu BSON **Decimal128**, index trên field **price** không biến string thành decimal đúng kiểu. Cần mapping dữ liệu nhất quán. Tương tự, index không khắc phục được query luôn lọc sai tenant hoặc field không tồn tại.

### 11.4. Đừng tạo index chỉ vì một truy vấn chậm

Một query chậm có thể do:

- thiếu index;
- index không phù hợp;
- query trả về quá nhiều document;
- projection lấy payload lớn;
- sort và pagination không tối ưu;
- network, disk, cache hoặc connection pool quá tải;
- tần suất update/replication gây tranh chấp tài nguyên;
- dữ liệu bị phân bố lệch giữa các shard.

Index là một đòn bẩy mạnh, nhưng phải đo đúng nguyên nhân trước khi thêm chỉ mục.

## 12. Một vòng đời quản lý index an toàn

Giả sử hệ thống dự định bổ sung index để hỗ trợ endpoint danh sách sản phẩm theo category/status.

### Bước 1 — Mô tả query thực tế

~~~javascript
db.products.find(
  {
    tenantId: "SHOP-A",
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    name: 1,
    price: 1
  }
).sort({ createdAt: -1 }).limit(50);
~~~

Query này có filter và sort. Không nên tạo index **{category:1}** chỉ vì thấy field category xuất hiện; cần cân nhắc tenantId, status, createdAt, sort direction, projection, selectivity và workload.

### Bước 2 — Đọc index catalog

~~~javascript
db.products.getIndexes();
~~~

Tìm xem có index nào đã hỗ trợ phần lớn query pattern. Tránh tạo những index trùng vai trò hoặc quá nhiều biến thể gần giống.

### Bước 3 — Kiểm tra query plan hiện tại

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  category: "ACCESSORIES",
  status: "ACTIVE"
}).sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
~~~

Ghi các chỉ số cần thiết và hiểu cách truy vấn hoạt động trong môi trường thử nghiệm có dữ liệu đại diện.

### Bước 4 — Chọn index cho workload

Một ứng viên:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    category: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "ix_tenant_category_status_created"
  }
);
~~~

Đây là **ứng viên để đo**, không phải tuyên bố luôn tối ưu. Thứ tự field có thể thay đổi tùy selectivity, các query khác và chính sách pagination. Cân nhắc nguyên tắc equality, sort, range khi thiết kế compound index.

### Bước 5 — Đọc lại index specification

~~~javascript
db.products.getIndexes().find(
  index => index.name === "ix_tenant_category_status_created"
);
~~~

Xác nhận key pattern đúng thứ tự và options đã định nghĩa.

### Bước 6 — Đo lại và quan sát tải

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  category: "ACCESSORIES",
  status: "ACTIVE"
}).sort({ createdAt: -1 })
  .limit(50)
  .explain("executionStats");
~~~

Đánh giá:

- Kế hoạch query có phù hợp không?
- keysExamined/docsExamined có giảm?
- p95/p99 latency từ ứng dụng có cải thiện?
- write latency và dung lượng index tăng bao nhiêu?
- Có regression ở các endpoint quan trọng khác không?

### Bước 7 — Nếu bỏ index, thử ẩn trước

~~~javascript
db.products.hideIndex("ix_tenant_category_status_created");
~~~

Giám sát hiệu năng và query plans một khoảng đủ đại diện, rồi:

~~~javascript
// Nếu phải khôi phục ngay:
db.products.unhideIndex("ix_tenant_category_status_created");

// Chỉ drop sau khi có bằng chứng và được phê duyệt:
// db.products.dropIndex("ix_tenant_category_status_created");
~~~

Không áp dụng quy trình hide/drop cho **_id_**.

## 13. Java Sync Driver: tạo, liệt kê và xóa index

Trong ứng dụng Java dùng **MongoDB Java Sync Driver**, có thể quản lý index bằng API của **MongoCollection**. Ưu điểm là dùng các builder typed như **Indexes**, **IndexOptions** thay vì ghép chuỗi JSON.

Ví dụ sau giả định đã có dependency MongoDB Java Sync Driver và một **MongoClient** được cấu hình hợp lệ.

### 13.1. createIndex() trong Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public final class IndexCreateExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                    "MONGODB_URI environment variable is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("index_basics_lab");

            MongoCollection<Document> collection =
                    database.getCollection("products");

            IndexOptions options = new IndexOptions()
                    .name("ix_category_status");

            String indexName = collection.createIndex(
                    Indexes.ascending("category", "status"),
                    options
            );

            System.out.println("Index name: " + indexName);
        }
    }
}
~~~

Java driver gửi createIndexes command phù hợp qua collection API. Việc triển khai trên collection đang có dữ liệu có thể làm server cần xây dựng index; không nên cho ứng dụng xử lý request tạo index lớn tùy tiện theo mỗi HTTP call.

### 13.2. createIndex() unique theo tenant

~~~java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

String indexName = collection.createIndex(
        Indexes.ascending("tenantId", "productCode"),
        new IndexOptions()
                .name("uq_tenant_product_code")
                .unique(true)
);

System.out.println(indexName);
~~~

Nếu dữ liệu trùng cặp **tenantId/productCode**, driver nhận lỗi từ MongoDB. Cần xử lý exception cụ thể, không tự động xóa document trùng trước khi đã đánh giá nghiệp vụ.

### 13.3. listIndexes() thay cho getIndexes()

Java Sync Driver cung cấp **listIndexes()**:

~~~java
for (Document indexSpec : collection.listIndexes()) {
    System.out.println(indexSpec.toJson());
}
~~~

**mongosh** dùng **getIndexes()**, còn Java driver thường dùng **listIndexes()**. Đây là hai giao diện khác nhau nhưng cùng mục tiêu quan sát index catalog của collection.

Lọc tên index:

~~~java
boolean exists = false;

for (Document spec : collection.listIndexes()) {
    if ("ix_category_status".equals(spec.getString("name"))) {
        exists = true;
        System.out.println(spec.toJson());
    }
}

System.out.println("Exists: " + exists);
~~~

Khi cần bảo đảm index theo schema migration, cũng phải so sánh **key/options**, không chỉ tên.

### 13.4. dropIndex() bằng Java

~~~java
collection.dropIndex("ix_category_status");
~~~

Lệnh yêu cầu MongoDB gỡ index cụ thể. Phải kiểm soát quyền vận hành và thời điểm thực hiện. Trong production, thông thường nên dùng migration/admin workflow thay vì xóa index khi service nhận request từ client.

### 13.5. Ví dụ một phương thức “ensure” có giới hạn

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public final class ProductIndexMigration {
    public static void ensureIndex(MongoCollection<Document> collection) {
        collection.createIndex(
                Indexes.ascending("tenantId", "productCode"),
                new IndexOptions()
                        .name("uq_tenant_product_code")
                        .unique(true)
        );
    }
}
~~~

Phương thức này có thể được gọi trong một migration có điều phối. Nó **không phải bộ quản lý schema hoàn chỉnh**: không tự phát hiện mọi drift về options/collation, không điều phối nhiều process, không giải quyết duplicate data và không giám sát build. Với hệ thống lớn cần quy trình deployment rõ ràng.

### 13.6. API Java không thay thế hiểu biết về hành vi server

Khi một service gọi:

~~~java
collection.dropIndex("uq_tenant_product_code");
~~~

MongoDB không chỉ bỏ một cấu trúc tăng tốc, mà còn bỏ ràng buộc unique do index đó đảm nhiệm. Java type safety không ngăn được thay đổi semantics nghiệp vụ của database. Cần xem index như một phần của database schema và security/operational model.

## 14. Spring Data MongoDB: IndexOperations

Với **Spring Data MongoDB**, có thể khai báo index qua annotation hoặc điều khiển bằng **MongoTemplate.indexOps()**. Dùng annotation có thể thuận tiện, nhưng index creation và các migration vẫn phải được kiểm soát.

### 14.1. Khai báo entity và field _id

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class ProductDocument {
    @Id
    private String id;

    private String tenantId;
    private String productCode;
    private String category;
    private String status;

    // constructors, getters, setters
}
~~~

Field **id** được Spring Data ánh xạ vào MongoDB **_id** theo quy ước/annotation. Trường **id** trong Java là **String** ở ví dụ này; cách chuyển đổi sang ObjectId/string khi lưu có thể phụ thuộc cơ chế mapping Spring Data và giá trị. Nếu nghiệp vụ yêu cầu kiểu _id chính xác, cần khai báo converter/annotation và contract nhất quán.

### 14.2. Tạo index bằng IndexOperations

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

// MongoTemplate mongoTemplate đã được inject.
mongoTemplate.indexOps("products").ensureIndex(
        new Index()
                .on("category", Sort.Direction.ASC)
                .on("status", Sort.Direction.ASC)
                .named("ix_category_status")
);
~~~

Phương thức **ensureIndex** bảo đảm index tương ứng trong những điều kiện được hỗ trợ, nhưng không được hiểu là có thể thay đổi mọi option của một index tồn tại mà không cần migration.

### 14.3. Liệt kê index bằng Spring Data

~~~java
mongoTemplate.indexOps("products")
        .getIndexInfo()
        .forEach(System.out::println);
~~~

Spring Data trả về các đối tượng **IndexInfo** mô tả index thay vì cùng dạng **getIndexes()** của mongosh. Những thông tin có thể bao gồm tên, field, unique và các options khác.

### 14.4. Gỡ index bằng Spring Data

~~~java
mongoTemplate.indexOps("products")
        .dropIndex("ix_category_status");
~~~

Không nên đặt câu lệnh này trong luồng xử lý request bình thường hoặc chạy ở mọi instance khi application khởi động nếu chưa có điều phối.

### 14.5. Annotation @Indexed và @CompoundIndex

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
@CompoundIndex(
        name = "uq_tenant_product_code",
        def = "{ 'tenantId': 1, 'productCode': 1 }",
        unique = true
)
public class ProductEntity {
    @Id
    private String id;

    private String tenantId;
    private String productCode;

    @Indexed(name = "ix_category")
    private String category;
}
~~~

Khai báo annotation **mô tả index mong muốn**, nhưng việc tự động tạo index lúc startup phụ thuộc **cấu hình auto-index creation** và phiên bản Spring Data. Spring Data MongoDB hiện đại không nên được mặc định xem là luôn tự tạo tất cả index chỉ vì có annotation. Trong production, nên quyết định rõ dùng annotation với cơ chế tạo index được bật có kiểm soát hay migration riêng.

Một rủi ro là **đổi annotation hoặc đổi tên Java field không tự động drop index cũ**. Các index dư có thể tích lũy nếu không có lifecycle management.

## 15. _id index và sharding: giới hạn uniqueness toàn cluster

Trong một **unsharded collection**, unique index **_id** giúp ngăn hai document có cùng _id.

Với **sharded collection**, cần phân biệt:

- Nếu shard key được chọn là **_id**, các thao tác định tuyến và uniqueness của ID có mối quan hệ trực tiếp phù hợp với cấu trúc sharding.
- Nếu **_id không phải shard key**, MongoDB có thể chỉ cưỡng chế uniqueness của **_id** trên **mỗi shard**, không bảo đảm duy nhất toàn cluster cho các thao tác có thể phân phối đến shard khác nhau. Trong trường hợp đó, **ứng dụng chịu trách nhiệm bảo đảm _id toàn cục không trùng**.
- Unique index trên sharded collection phải tuân theo các yêu cầu về **shard key prefix** và những giới hạn được MongoDB hỗ trợ.

Ví dụ giả định shard key là **tenantId**. Hai document có cùng _id nhưng tenantId khác nhau có khả năng được định tuyến đến hai shard khác; không nên dựa vào index _id cục bộ để bảo đảm uniqueness toàn cluster nếu _id không thuộc shard key theo yêu cầu.

**Thiết kế an toàn:**

1. Dùng quy tắc sinh ID có xác suất trùng cực thấp như ObjectId/UUID đúng cách nếu phù hợp.
2. Nếu business yêu cầu uniqueness toàn cluster theo một khóa cụ thể, nghiên cứu shard key và index design ngay từ đầu.
3. Không đánh đồng **một index tồn tại trên mỗi shard** với **một global unique constraint**.
4. Kiểm tra đặc tính chính xác với topology, phiên bản MongoDB và kiểu collection đang triển khai.

Không nên tự thay shard key chỉ để sửa một truy vấn chậm mà không đánh giá data distribution, routing, availability và migration.

## 16. Một số loại index khác để đặt createIndex trong đúng bối cảnh

Bài học tập trung **_id**, **createIndex**, **getIndexes** và **dropIndex**. Khi quản lý index, bạn sẽ gặp nhiều loại chỉ mục; cần nhận biết để không xóa/sửa sai.

| Loại index | Ví dụ key/option | Công dụng tiêu biểu |
|---|---|---|
| **Single-field** | **{category:1}** | Filter/sort theo một field. |
| **Compound** | **{tenantId:1,status:1}** | Truy vấn theo nhiều field/prefix. |
| **Multikey** | **{tags:1}** khi tags là mảng | Tìm phần tử trong array. |
| **Unique** | **unique:true** | Ngăn giá trị khóa trùng theo phạm vi. |
| **Partial** | **partialFilterExpression** | Index tập con document theo predicate. |
| **TTL** | **expireAfterSeconds** | Xóa tài liệu hết hạn bất đồng bộ. |
| **Text** | **{description:"text"}** | Hỗ trợ tìm kiếm văn bản theo cơ chế text index của MongoDB. |
| **Wildcard** | **{"attributes.$**":1}** | Truy vấn field động trong document trong những trường hợp phù hợp. |
| **Geospatial** | **{"location":"2dsphere"}** | Truy vấn dữ liệu địa lý. |
| **Hashed** | **{customerId:"hashed"}** | Truy vấn/phân bố liên quan khóa băm; có giới hạn về loại truy vấn. |

Các lựa chọn như **Atlas Search indexes** là cấu trúc tìm kiếm riêng của hệ sinh thái MongoDB và có công cụ/quy trình quản lý khác **createIndex** B-tree thông thường. Đừng dùng **dropIndex** cho một search index nếu API quản lý của loại index đó khác.

Ngoài ra một index không nhất thiết “tốt” cho mọi query chỉ vì nó có nhiều field. Compound indexes quá dài có thể tiêu tốn dung lượng và không phù hợp với các query không theo prefix được khai báo.

## 17. Các lỗi thường gặp khi quản lý index

### 17.1. Tạo lại index _id dù đã tồn tại

~~~javascript
db.products.createIndex({ _id: 1 });
~~~

Trên collection thông thường, index **_id_** đã tồn tại; gọi thêm không đem lại lợi ích tối ưu đáng kể. Hãy kiểm tra **getIndexes()** trước khi thêm index cho các field khác.

### 17.2. Nhầm _id index với unique business key

Hai product có **_id khác nhau** nhưng cùng **productCode** vẫn có thể được insert, trừ khi có một unique constraint/index phù hợp trên productCode hoặc tổ hợp business key.

~~~javascript
{
  _id: "P-001",
  productCode: "KEYBOARD-01"
}

{
  _id: "P-002",
  productCode: "KEYBOARD-01"
}
~~~

Nếu cần uniqueness theo tenant, phải thiết kế index **{tenantId:1,productCode:1}** với option **unique:true**, xét thêm giới hạn sharding khi có.

### 17.3. Tạo unique index sau khi đã có dữ liệu trùng

~~~javascript
db.products.createIndex(
  { productCode: 1 },
  { unique: true }
);
~~~

Lệnh có thể lỗi duplicate key. Không nên xóa ngẫu nhiên “document trùng” để tạo index; cần xác định bản ghi đúng, tác động downstream và kế hoạch migration trước.

### 17.4. Chỉ xem tên, bỏ qua options

Một index có tên **ix_active_category** nhưng **partialFilterExpression** khác ý định là hai hợp đồng khác nhau. Một migration cần so sánh specification chứ không chỉ gọi **getIndexes().map(i => i.name)**.

### 17.5. Nhầm dropIndex với xóa document

**dropIndex()** gỡ chỉ mục, không xóa document. Nhưng gỡ **unique/TTL** có thể làm thay đổi các bất biến dữ liệu hay retention policy, nên vẫn là thao tác nhạy cảm.

### 17.6. Xóa index _id_

Index _id của collection thông thường là index bắt buộc; MongoDB không cho drop. Không nên cố thay đổi bằng công cụ truy cập trực tiếp tệp WiredTiger.

### 17.7. Tạo quá nhiều index vì muốn mọi query đều nhanh

Index tăng chi phí ghi và dung lượng. Tạo nhiều index đơn **{a:1}**, **{b:1}**, **{c:1}** không có nghĩa chúng tự động tốt hơn một compound index phù hợp với access pattern. Đo workload và thiết kế số lượng index tối thiểu đáp ứng SLA.

### 17.8. Xóa index chỉ vì $indexStats ít lượt truy cập

Một index phục vụ báo cáo tháng có thể không được dùng suốt tuần trước đó. Một unique index cũng có thể cần giữ để cưỡng chế invariant ngay cả khi ít query đọc sử dụng.

### 17.9. Dùng drop rồi create để đổi options trong giờ cao điểm

Điều này có thể tạo một khoảng thời gian **không có index**, khiến query chậm và ràng buộc unique không được bảo vệ trong thời gian đó. Các bước thay đổi index phải được lên kế hoạch theo loại option, khả năng dùng **collMod**, duplicate data, quyền và thời gian build.

### 17.10. Dùng hint ép index không còn phù hợp

MongoDB hỗ trợ **hint()** để yêu cầu dùng index cụ thể trong một số truy vấn. Nếu code production ép hint theo tên index và index đó bị drop, query có thể thất bại. Khi quản lý index, phải tìm các truy vấn và ứng dụng sử dụng hint tương ứng.

~~~javascript
db.products.find({
  category: "ACCESSORIES"
}).hint("ix_category_status");
~~~

Trong ví dụ trên, hint phụ thuộc index có tên **ix_category_status**. Nếu index đã bị gỡ, cần cập nhật query/hint phù hợp. Không nên lạm dụng hint thay vì để query planner chọn và đo hiệu năng thực tế.

## 18. Bài thực hành: quản lý vòng đời index trong mongosh

Hãy làm trên database **index_basics_lab** dành riêng cho lab.

### Bước 1 — Tạo collection và xem _id index

~~~javascript
use index_basics_lab

db.createCollection("index_practice");
db.index_practice.getIndexes();
~~~

Kỳ vọng thấy index tên **_id_**. Nếu collection đã tồn tại, bỏ bước createCollection.

### Bước 2 — Thêm document

~~~javascript
db.index_practice.insertMany([
  {
    _id: "P-101",
    tenantId: "SHOP-A",
    productCode: "MOUSE-01",
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    _id: "P-102",
    tenantId: "SHOP-A",
    productCode: "KEYBOARD-01",
    category: "ACCESSORIES",
    status: "ACTIVE"
  },
  {
    _id: "P-103",
    tenantId: "SHOP-A",
    productCode: "MONITOR-01",
    category: "DISPLAYS",
    status: "DRAFT"
  }
]);
~~~

### Bước 3 — Tìm theo _id

~~~javascript
db.index_practice.find({
  _id: "P-102"
}).explain("executionStats");
~~~

Quan sát query plan và những trường **nReturned**, **totalKeysExamined**, **totalDocsExamined**. Với một collection rất nhỏ, plan có thể khác kỳ vọng đơn giản tùy phiên bản, nhưng index **_id_** vẫn có sẵn.

### Bước 4 — Tạo index thường

~~~javascript
db.index_practice.createIndex(
  { category: 1, status: 1 },
  { name: "ix_practice_category_status" }
);
~~~

### Bước 5 — Đọc metadata

~~~javascript
db.index_practice.getIndexes();
~~~

Tìm **key: {category:1,status:1}** và **name: ix_practice_category_status**.

### Bước 6 — Tạo unique index cho mã sản phẩm theo tenant

~~~javascript
db.index_practice.createIndex(
  { tenantId: 1, productCode: 1 },
  {
    name: "uq_practice_tenant_product_code",
    unique: true
  }
);
~~~

Thử insert một document mới có **_id khác** nhưng trùng **tenantId + productCode**:

~~~javascript
db.index_practice.insertOne({
  _id: "P-999",
  tenantId: "SHOP-A",
  productCode: "MOUSE-01",
  category: "ACCESSORIES",
  status: "ACTIVE"
});
~~~

Kỳ vọng bị từ chối vì **duplicate key** trên unique index mới, dù **_id** không trùng.

### Bước 7 — So sánh query plan

~~~javascript
db.index_practice.find({
  category: "ACCESSORIES",
  status: "ACTIVE"
}).explain("executionStats");
~~~

Query nhỏ có thể vẫn chọn **COLLSCAN** vì chi phí thấp. Hãy ghi nhận plan và không suy ra kết luận benchmark từ ba document.

### Bước 8 — Ẩn và hiện lại index

~~~javascript
db.index_practice.hideIndex("ix_practice_category_status");
db.index_practice.getIndexes();

db.index_practice.unhideIndex("ix_practice_category_status");
db.index_practice.getIndexes();
~~~

Chỉ thử hide/unhide trên index **thường**, không phải **_id_**.

### Bước 9 — Drop index thử nghiệm

~~~javascript
db.index_practice.dropIndex("ix_practice_category_status");
db.index_practice.getIndexes();
~~~

Kỳ vọng **ix_practice_category_status** không còn được liệt kê; **_id_** và unique index còn lại vẫn tồn tại. Khi xóa index thường, các document không bị mất.

### Bước 10 — Kiểm tra _id index không thể drop

~~~javascript
db.index_practice.dropIndex("_id_");
~~~

MongoDB từ chối thao tác. Không cần tìm cách sửa hay xóa file dữ liệu để thử nghiệm thêm.

## 19. Bài tập tình huống và câu hỏi ôn tập

### Tình huống 1 — Có cần index trên _id không?

Một ứng dụng lưu 5 triệu customer document. API luôn lấy thông tin một khách hàng bằng **_id**. Đồng nghiệp đề xuất:

~~~javascript
db.customers.createIndex({ _id: 1 });
~~~

Hãy giải thích vì sao đây không phải index mới cần thiết trên collection thông thường, và nên dùng công cụ nào để xác nhận.

### Tình huống 2 — Duplicate business code

Hai customer có _id khác nhau nhưng cùng **customerCode** vẫn được lưu. Hãy đề xuất unique index:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, customerCode: 1 },
  { unique: true, name: "uq_tenant_customer_code" }
);
~~~

Nếu dữ liệu cũ có duplicate, cần làm gì trước khi chạy migration?

### Tình huống 3 — Index báo ít lượt truy cập

Index **ix_monthly_report** không được dùng trong 14 ngày gần nhất. Có được xóa ngay không? Hãy nêu lý do cần xem lịch báo cáo, unique constraints, query hint, thời gian quan sát và kế hoạch khôi phục.

### Tình huống 4 — Query bị chậm sau drop

Một team gỡ **ix_category_status** vì thấy “không cần”. Sau deploy, endpoint lọc category/status tăng latency từ vài chục đến hàng trăm mili giây. Hãy mô tả quy trình khảo sát với **getIndexes**, **explain**, phương án rollback và những tác động vận hành của việc phải build lại index.

### Tình huống 5 — Tenant-specific uniqueness trong sharded cluster

Collection shard theo **tenantId**, ID tự sinh từ nhiều service. Tại sao cần xem xét tính duy nhất toàn cluster của **_id** và các giới hạn unique index theo shard key? Đề xuất nguyên tắc sinh ID và xác nhận data model trước khi sharding.

### Câu hỏi tự kiểm tra

1. Vì sao MongoDB tạo index **_id_** tự động?
2. **_id** có bắt buộc là ObjectId không? Vì sao kiểu BSON của _id quan trọng khi truy vấn?
3. **createIndex()** và **getIndexes()** phục vụ hai mục tiêu khác nhau thế nào?
4. Index **{category:1,status:1}** khác **{status:1,category:1}** ở đâu?
5. Nếu tạo unique index khi collection đã chứa duplicate key, điều gì có thể xảy ra?
6. Có thể dùng **dropIndex("_id_")** trên collection thông thường không?
7. **dropIndex()** có xóa document hay không? Tại sao drop unique index vẫn nguy hiểm?
8. **getIndexes()** có chứng minh một index đang được query planner sử dụng thường xuyên không? Cần công cụ nào khác?
9. Vì sao index có thể làm write latency tăng dù query đọc nhanh hơn?
10. Khi nào nên cân nhắc **hidden index** thay vì drop ngay?
11. Vì sao projection **_id: 0** có thể quan trọng khi phân tích covered query?
12. Index **_id_** có luôn cưỡng chế uniqueness toàn sharded cluster nếu _id không phải shard key không?
13. Một API có **hint** theo tên index sẽ bị ảnh hưởng gì nếu index đó bị drop?
14. Tại sao không nên xem migration index như một thao tác “an toàn tuyệt đối” chỉ vì chạy được bằng một dòng createIndex?

## 20. Tổng kết

Một collection MongoDB thông thường đã có **index trên _id** ngay từ khi được tạo. Index này hỗ trợ truy vấn theo định danh và cưỡng chế uniqueness theo phạm vi MongoDB bảo đảm. Nó không thay thế những index dành cho business keys, field lọc, sort hoặc những ràng buộc khác.

Ba thao tác quản lý index cơ bản:

~~~javascript
// 1. Tạo index cho query pattern thực tế.
db.products.createIndex(
  { category: 1, status: 1 },
  { name: "ix_category_status" }
);

// 2. Liệt kê, kiểm tra key và options.
db.products.getIndexes();

// 3. Gỡ index không còn cần thiết, sau khi đánh giá tác động.
db.products.dropIndex("ix_category_status");
~~~

**Những nguyên tắc quan trọng:**

1. **Đừng tạo lại _id index** chỉ vì muốn query theo _id nhanh hơn; nó đã tồn tại ở collection thông thường.
2. **Đừng nhầm _id unique với business key unique**; dùng unique index khác khi domain yêu cầu và xem xét sharding.
3. **Tạo index từ access patterns**, gồm filter, sort, projection và tần suất truy vấn.
4. **Đặt tên index có ý nghĩa** để dễ quản lý qua migration.
5. **getIndexes kiểm tra định nghĩa**, còn **explain/$indexStats/metrics** giúp hiểu tác dụng và việc sử dụng.
6. **Drop index không xóa document**, nhưng có thể xóa ràng buộc unique/TTL và làm query chậm đi.
7. **Ưu tiên thử hide** khi cần đánh giá ảnh hưởng của việc bỏ index, rồi mới drop nếu thực sự phù hợp.
8. **Đo chi phí ghi và dung lượng**, vì nhiều index có thể khiến mỗi insert/update/delete tốn kém hơn.
9. **Đừng phụ thuộc vào giả định phiên bản cũ** về cách index build/auto index creation; kiểm tra MongoDB và driver đang vận hành.
10. **Quản lý index như một phần của database schema và quy trình deployment**, không phải lệnh tiện tay chạy từ bất kỳ request nào.

### Tài liệu chính thức để đọc tiếp

- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — tổng quan index và các loại index.
- [Default _id Index](https://www.mongodb.com/docs/manual/indexes/#default-id-index) — index _id được tạo mặc định.
- [db.collection.createIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/) — tham số, options và hành vi tạo index.
- [db.collection.getIndexes()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/) — liệt kê index specification.
- [db.collection.dropIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.dropIndex/) — gỡ index.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/) — hide/unhide để đánh giá tác động.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — đọc query plan và executionStats.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness và những giới hạn.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — **createIndex**, **listIndexes**, **dropIndex**.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — **IndexOperations**, **@Indexed**, **@CompoundIndex**.

Trong ứng dụng Java/Spring Data, hãy phân biệt **định nghĩa index mong muốn** với **index thực sự tồn tại trên MongoDB**. Mỗi lần thêm, thay hoặc xóa index nên được coi là một thay đổi có tác động đến cả tính đúng đắn của dữ liệu lẫn hiệu năng hệ thống.
