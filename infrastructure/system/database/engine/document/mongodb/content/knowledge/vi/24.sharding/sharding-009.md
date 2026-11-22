# Ràng buộc _id, unique index và tính duy nhất trên toàn cụm trong MongoDB Sharding

## 1. Mục tiêu bài học

Trong MongoDB, nhiều ứng dụng sử dụng `_id`, `email`, `username` hay `orderNumber` như những khóa cần duy nhất. Trên collection chưa sharded, một unique index có thể kiểm tra các document của collection đó. Khi collection được phân phối qua nhiều shards, một câu hỏi quan trọng xuất hiện:

**Nếu hai document có cùng email nhưng nằm ở hai shards khác nhau, shard nào phát hiện khóa đã bị trùng?**

MongoDB giải quyết bằng các quy tắc riêng về unique indexes liên quan đến **shard key**. Đặc biệt, default unique index `_id_` không nhất thiết bảo đảm `_id` duy nhất **trên toàn sharded cluster** nếu `_id` không phải shard key.

Bài học thuộc chương **Sharding** của module **Database Engine Document MongoDB**, với đề bài **Ràng buộc _id, unique index và tính duy nhất trên toàn cụm**.

Sau bài này, bạn có thể:

1. Phân biệt unique trong một shard, unique của sharded collection và unique xuyên nhiều collections.
2. Giải thích trường hợp `_id` chỉ được kiểm tra duy nhất theo từng shard.
3. Áp dụng quy tắc **full shard-key prefix** khi tạo unique indexes.
4. Thiết kế unique theo tenant khác với unique trên toàn hệ thống.
5. Tạo collection range-sharded và compound unique index hợp lệ.
6. Nhận biết những index không hợp lệ và unique constraint trên hashed index.
7. Thiết kế proxy collection kết hợp transaction khi business key không thể là shard key.
8. Hiểu mối quan hệ của collation, giá trị thiếu/null, canonicalization và business uniqueness.
9. Xử lý duplicate key trong mongosh và Java Driver, kể cả request được retry.
10. Dự đoán ảnh hưởng của shard key change, resharding, chunk migration và các bước vận hành.

**Nguyên tắc trung tâm:** Trên range-sharded collection, unique index thông thường phải có **toàn bộ shard key làm tiền tố**. Ngoại lệ `_id` mặc định có thể chỉ bảo đảm duy nhất **trong từng shard** khi `_id` không phải shard key.

## 2. Vì sao sharding làm bài toán unique phức tạp?

Một collection chưa sharded:

~~~text
Application
     |
     v
MongoDB collection
     |
     +-- unique index(email)
           kiểm tra document của collection
~~~

Một collection đã sharded:

~~~text
                       Application
                            |
                            v
                           mongos
                            |
                 +----------+----------+
                 |                     |
                 v                     v
              Shard A               Shard B
           local index            local index
           user email=X           user email=X?
~~~

Trong collection sharded, mỗi shard quản lý những chunk dữ liệu mà nó sở hữu. Mỗi shard có thể kiểm tra unique index trên các document **của chính shard đó**, nhưng không thể mặc nhiên kiểm tra mọi giá trị ở tất cả shards.

Để bảo đảm unique toàn collection mà không cần một global lookup tùy ý cho mọi insert, MongoDB yêu cầu cấu trúc index bảo đảm những document có cùng full unique key phải được định tuyến theo cùng shard key.

### 2.1. Những phạm vi uniqueness khác nhau

| Phạm vi | Nghĩa |
|---|---|
| Unique trong shard | Hai document cùng shard không được có cùng index key |
| Unique trên sharded collection | Hai document, dù ở shard nào, không được có cùng index key |
| Unique trong tenant | Chỉ không được trùng trong một tenant, tenant khác có thể dùng lại |
| Unique toàn hệ thống | Không được trùng dù thuộc tenant nào; có thể cần registry |
| Unique xuyên databases/clusters | Một index trên một collection không tự kiểm tra dữ liệu ở collection hoặc cluster khác |

**“Unique toàn cụm” trong bài** chủ yếu nói về các shards chứa **cùng một collection logic**. Nó không tự bao trùm mọi collection của nhiều database độc lập.

### 2.2. Shard key khác unique key

**Shard key** quyết định cách MongoDB phân phối document. **Unique key** quyết định những giá trị nào không được trùng.

Hai khái niệm có thể là cùng một field, ví dụ:

~~~javascript
shardKey = { orderNumber: 1 };
uniqueKey = { orderNumber: 1 };
~~~

Hoặc có thể khác:

~~~javascript
shardKey = { tenantId: 1 };
uniqueKey = { tenantId: 1, emailKey: 1 };
~~~

Phương án thứ hai bảo đảm **cặp** tenantId và emailKey duy nhất, không bảo đảm emailKey duy nhất toàn cluster.

## 3. Shard-key prefix là gì?

Giả sử collection shard theo:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

Một compound index có shard key làm prefix:

~~~javascript
{ tenantId: 1, regionId: 1, emailKey: 1 }
~~~

Một index chứa các field đó nhưng **sai thứ tự**:

~~~javascript
{ tenantId: 1, emailKey: 1, regionId: 1 }
~~~

Một index thiếu một phần shard key:

~~~javascript
{ tenantId: 1, emailKey: 1 }
~~~

Hai index sau không đáp ứng quy tắc full shard-key prefix của unique index cho shard key `{tenantId:1,regionId:1}`.

### 3.1. Phải là toàn bộ prefix, không phải một field có mặt ở đâu đó

Nếu shard key gồm ba field:

~~~javascript
{ tenantId: 1, regionId: 1, orderType: 1 }
~~~

thì unique index hợp lệ về prefix có thể là:

~~~javascript
{ tenantId: 1, regionId: 1, orderType: 1, orderNo: 1 }
~~~

Không đủ:

~~~javascript
{ tenantId: 1, regionId: 1, orderNo: 1 }
~~~

vì thiếu `orderType` ở vị trí prefix bắt buộc.

### 3.2. Vì sao prefix cho phép kiểm tra unique?

Khi hai document có cùng toàn bộ unique index key gồm prefix shard key, chúng cũng có cùng shard key. Theo cơ chế routing, các giá trị này thuộc cùng phạm vi phân bố mà shard có thể kiểm tra nhất quán.

Đây là lý do MongoDB không cho tạo tùy ý unique index chỉ trên field không phải shard key trong range-sharded collection.

## 4. Những unique index được cho phép trên range-sharded collection

Theo MongoDB Manual, nhóm quan trọng gồm:

1. Unique index trên chính **shard key**.
2. Unique compound index bắt đầu bằng **toàn bộ shard key**.
3. Default unique `_id` index — một ngoại lệ, **không nhất thiết unique toàn cluster**.

Với shard key:

~~~javascript
{ tenantId: 1 }
~~~

| Index | Dùng unique? | Ý nghĩa |
|---|---|---|
| `{tenantId:1}` | Có thể | Chỉ một document trên mỗi tenantId |
| `{tenantId:1,emailKey:1}` | Có thể | Một emailKey trong một tenant |
| `{tenantId:1,orderNo:1}` | Có thể | Một orderNo trong một tenant |
| `{emailKey:1}` | Không, với unique=true | Không có shard-key prefix |
| `{emailKey:1,tenantId:1}` | Không, với unique=true | Thứ tự field sai |
| `{tenantId:1,emailKey:1}` | Có thể nếu unique=false | Index thường, không chống trùng |
| `{_id:1}` | Default unique index | Có thể chỉ bảo đảm trong từng shard |

**Không được suy luận** rằng một index “có field shard key ở đâu đó” là đủ; thứ tự prefix quyết định tính hợp lệ.

### 4.1. Unique compound kiểm tra tổ hợp, không từng trường

Unique:

~~~javascript
{ tenantId: 1, emailKey: 1 }
~~~

cho phép:

~~~javascript
{
  tenantId: "tenant-A",
  emailKey: "hello@example.test"
}

{
  tenantId: "tenant-B",
  emailKey: "hello@example.test"
}
~~~

vì hai **tổ hợp** khác nhau.

Không cho phép:

~~~javascript
{
  tenantId: "tenant-A",
  emailKey: "hello@example.test"
}

{
  tenantId: "tenant-A",
  emailKey: "hello@example.test"
}
~~~

vì cặp trùng hoàn toàn, dù `_id` hoặc các field khác khác nhau.

### 4.2. Unique shard key chỉ bảo đảm toàn tổ hợp

Với shard key:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

unique trên chính shard key chỉ bảo đảm cặp `tenantId,regionId` là duy nhất. Nó không làm từng tenantId hay regionId thành unique riêng lẻ.

## 5. Ngoại lệ quan trọng: _id không luôn unique trên toàn sharded cluster

Một collection MongoDB mặc định có index:

~~~javascript
{
  key: { _id: 1 },
  name: "_id_",
  unique: true
}
~~~

Với collection chưa sharded, nó bảo đảm `_id` duy nhất trong collection.

Nhưng nếu collection đã shard theo:

~~~javascript
{ tenantId: 1 }
~~~

MongoDB chỉ enforce default `_id` uniqueness **trên từng shard**. Nó không có một global check cho `_id` bất kể giá trị tenantId.

### 5.1. Ví dụ hai document cùng _id

~~~javascript
{
  _id: "same-id",
  tenantId: "tenant-A",
  displayName: "Lan"
}

{
  _id: "same-id",
  tenantId: "tenant-B",
  displayName: "Minh"
}
~~~

Hai document **có thể** cùng tồn tại nếu chúng nằm trên hai shards khác nhau. Nếu được định tuyến tới **cùng shard**, unique `_id_` index tại shard đó có thể từ chối document thứ hai.

Vì vậy, đừng viết bài kiểm thử kỳ vọng duplicate `_id` **luôn** được chấp nhận chỉ vì tenantId khác nhau. Kết quả còn phụ thuộc vị trí chunks và phân phối dữ liệu.

### 5.2. Nếu _id chính là shard key?

Với collection shard theo đúng:

~~~javascript
{ _id: 1 }
~~~

giá trị `_id` cũng là giá trị shard key. MongoDB có thể enforce uniqueness trên toàn sharded collection qua index/routing phù hợp.

Đây là ví dụ rõ ràng, nhưng phải đánh giá lựa chọn ranged sharding theo ID tăng tuần tự vì có thể tạo vùng ghi nóng.

### 5.3. ObjectId hoặc UUID có giải quyết hoàn toàn không?

Một `ObjectId`/UUID được sinh bằng generator đáng tin cậy có khả năng va chạm cực thấp. Đây là thực hành hữu ích để tránh tự tái sử dụng ID giữa nhiều tenant hoặc node.

~~~javascript
db.usersByTenant.insertOne({
  _id: new ObjectId(),
  tenantId: "tenant-A",
  displayName: "Lan"
});
~~~

Nhưng **xác suất trùng rất thấp khác một ràng buộc database global unique**.

Nếu ứng dụng import dữ liệu cũ, dùng counter được reset hoặc tự tạo một ID cố định nhiều lần, duplicate xuyên shards vẫn có thể xảy ra. Với yêu cầu tuyệt đối, cần một cơ chế uniqueness được enforce rõ.

### 5.4. _id là immutable

Sau khi document đã tồn tại, không thể sửa `_id` tùy ý bằng update thông thường:

~~~javascript
db.usersByTenant.updateOne(
  { tenantId: "tenant-A", _id: "user-001" },
  { $set: { _id: "user-002" } }
);
~~~

Việc thay định danh cần quy trình migration: tạo record mới, cập nhật tham chiếu và xóa record cũ phù hợp với bảo đảm nghiệp vụ.

### 5.5. Hệ quả với truy vấn

~~~javascript
db.usersByTenant.find({ _id: "same-id" });
~~~

Nếu ID đã trùng xuyên shards, truy vấn có thể trả hơn một document. `findOne({_id:...})` không phải bằng chứng ID global unique trên collection shard theo tenantId.

Khi identity là cặp tenant + ID, truy vấn nên có đầy đủ phạm vi:

~~~javascript
db.usersByTenant.findOne({
  tenantId: "tenant-A",
  _id: "same-id"
});
~~~

Điều này giúp routing và authorization đúng phạm vi, nhưng không biến `_id` thành global unique constraint.

## 6. Chuẩn bị môi trường thực hành

Những lệnh sharding yêu cầu **sharded cluster có mongos**. Không dùng một standalone mongod để chứng minh hành vi unique across shards.

~~~text
mongosh / Java Driver
         |
         v
        mongos
         |
    +----+----+
    |         |
  Shard A   Shard B
    |         |
    +----+----+
         |
    Config servers
~~~

### 6.1. Kiểm tra kết nối

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Kết quả trên `mongos` thường có:

~~~javascript
{
  msg: "isdbgrid"
}
~~~

Bạn cũng có thể đọc:

~~~javascript
sh.status();
~~~

Nếu không có quyền tạo collection hoặc shardCollection, hãy chỉ phân tích ví dụ. Không thử trên cluster production khi chưa có runbook.

### 6.2. Database mẫu

~~~javascript
use sharding_unique_lab
~~~

Bài sẽ dùng:

~~~text
sharding_unique_lab.usersByTenant
sharding_unique_lab.licenseCodes
sharding_unique_lab.emailClaims
~~~

Các tên này dành riêng cho **môi trường thử nghiệm**. Nếu collection tồn tại từ trước, kiểm tra metadata trước khi thay đổi; không tự drop collection chỉ vì muốn bắt đầu lại.

## 7. Demo tạo unique email theo tenant

**Yêu cầu:** Mỗi tenant chỉ có một tài khoản cho mỗi email chuẩn hóa, nhưng tenant khác được phép dùng cùng email.

Thiết kế:

~~~javascript
shardKey = { tenantId: 1 };
uniqueKey = { tenantId: 1, emailKey: 1 };
~~~

### 7.1. Tạo collection

~~~javascript
use sharding_unique_lab

db.createCollection("usersByTenant");
~~~

Nếu collection đã tồn tại, không chạy lại bước DDL một cách mù quáng.

### 7.2. Tạo index hỗ trợ shard key

~~~javascript
db.usersByTenant.createIndex(
  { tenantId: 1 },
  { name: "idx_tenant" }
);
~~~

### 7.3. Tạo unique compound index

~~~javascript
db.usersByTenant.createIndex(
  { tenantId: 1, emailKey: 1 },
  {
    name: "uniq_tenant_email",
    unique: true
  }
);
~~~

Index này là ràng buộc của **cặp tenantId/emailKey**. `tenantId` đứng đầu, đúng full shard key prefix.

### 7.4. Shard collection

Trên mongos:

~~~javascript
sh.shardCollection(
  "sharding_unique_lab.usersByTenant",
  { tenantId: 1 }
);
~~~

Đây là range sharding. Collection đã có index hỗ trợ shard key, và unique compound index tương thích với shard-key prefix.

### 7.5. Insert các giá trị hợp lệ

~~~javascript
db.usersByTenant.insertMany([
  {
    _id: "user-A-1",
    tenantId: "tenant-A",
    emailKey: "lan@example.test",
    displayName: "Lan A"
  },
  {
    _id: "user-B-1",
    tenantId: "tenant-B",
    emailKey: "lan@example.test",
    displayName: "Lan B"
  },
  {
    _id: "user-A-2",
    tenantId: "tenant-A",
    emailKey: "minh@example.test",
    displayName: "Minh"
  }
]);
~~~

Hai email `lan@example.test` ở hai tenants khác nhau được chấp nhận. Đây là **đúng** theo unique index của tổ hợp.

### 7.6. Insert trùng trong cùng tenant

~~~javascript
try {
  db.usersByTenant.insertOne({
    _id: "user-A-3",
    tenantId: "tenant-A",
    emailKey: "lan@example.test",
    displayName: "Duplicate"
  });
} catch (e) {
  print("Expected duplicate: " + e.message);
}
~~~

Document mới có cặp `("tenant-A","lan@example.test")` trùng với user-A-1, nên unique index từ chối. Lỗi thường có mã **11000** (`E11000 duplicate key`).

### 7.7. Truy vấn theo đúng tenant

~~~javascript
db.usersByTenant.findOne({
  tenantId: "tenant-A",
  emailKey: "lan@example.test"
});
~~~

Có shard key trong filter giúp `mongos` target được phạm vi dữ liệu phù hợp. Đây cũng là cách giữ đúng ngữ nghĩa dữ liệu multi-tenant.

## 8. Demo unique index không đúng prefix

Trên `usersByTenant` shard theo `{tenantId:1}`:

~~~javascript
// Bị từ chối vì không có shard key prefix.
db.usersByTenant.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

Một ví dụ cũng không hợp lệ:

~~~javascript
// Chứa tenantId nhưng thứ tự sai.
db.usersByTenant.createIndex(
  { emailKey: 1, tenantId: 1 },
  { unique: true }
);
~~~

Nếu bạn cần index để truy vấn theo email, index **không unique** vẫn có thể là lựa chọn hợp lệ:

~~~javascript
db.usersByTenant.createIndex(
  { emailKey: 1 }
);
~~~

Nhưng nó không chặn email trùng xuyên tenants.

### 8.1. Không thể dựa vào mongos tự quét mọi shard

`mongos` nhận request và định tuyến, nhưng không biến mọi unique index trên field tùy ý thành một phép dò global. Quy tắc prefix tồn tại chính vì không thể coi các unique indexes cục bộ ở mọi shard như một constraint thống nhất khi những key trùng có thể ở nhiều shards.

### 8.2. Nếu tạo unique trước khi sharding?

Nếu một unsharded collection đã có unique `{emailKey:1}`, rồi bạn muốn shard theo `{tenantId:1}`, `sh.shardCollection` có thể từ chối do unique index hiện tại không có shard-key prefix.

Không được coi quy tắc chỉ áp dụng cho những indexes tạo **sau** khi sharding.

## 9. Compound shard key và phạm vi unique

Giả sử shard key:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

| Index unique | Hợp lệ về prefix? | Phạm vi unique |
|---|---|---|
| `{tenantId:1,regionId:1}` | Có | Cặp tenant/region |
| `{tenantId:1,regionId:1,orderNo:1}` | Có | Bộ ba tenant/region/orderNo |
| `{tenantId:1,orderNo:1}` | Không | Thiếu regionId |
| `{tenantId:1,orderNo:1,regionId:1}` | Không | Thứ tự prefix sai |
| `{regionId:1,tenantId:1,orderNo:1}` | Không | Thứ tự shard key sai |
| `{orderNo:1}` | Không | Không có shard key |

### 9.1. Có nên thêm regionId vào shard key?

Nếu nghiệp vụ yêu cầu `orderNo` unique **trong tenant**, index `{tenantId,regionId,orderNo}` **không** đủ: cùng tenant/orderNo có thể được dùng ở hai region khác nhau.

Ví dụ:

~~~javascript
{ tenantId: "T1", regionId: "north", orderNo: "ORD-99" }
{ tenantId: "T1", regionId: "south", orderNo: "ORD-99" }
~~~

Bộ ba khác nhau nên hợp lệ.

Thiết kế shard key phải xét đồng thời phân bố dữ liệu, query pattern và **phạm vi uniqueness nghiệp vụ**.

## 10. Tạo unique constraint trên chính range shard key

Nếu mỗi `licenseCode` phải unique toàn collection và shard key là `licenseCode`:

~~~javascript
use sharding_unique_lab

db.createCollection("licenseCodes");

db.licenseCodes.createIndex(
  { licenseCode: 1 },
  {
    unique: true,
    name: "uniq_licenseCode"
  }
);
~~~

Sau đó:

~~~javascript
sh.shardCollection(
  "sharding_unique_lab.licenseCodes",
  { licenseCode: 1 },
  true
);
~~~

Đối số thứ ba `true` yêu cầu unique trên **chính shard key**.

### 10.1. Thử xung đột

~~~javascript
db.licenseCodes.insertOne({
  _id: "lic-1",
  licenseCode: "LIC-2026-001"
});

try {
  db.licenseCodes.insertOne({
    _id: "lic-2",
    licenseCode: "LIC-2026-001"
  });
} catch (e) {
  print(e.message);
}
~~~

Lệnh thứ hai bị từ chối vì trùng licenseCode.

### 10.2. Điều kiện cần chú ý

- Với collection không rỗng, phải chuẩn bị unique index shard key phù hợp trước.
- Nếu đã tồn tại một supporting index trên shard key nhưng **không unique**, tùy chọn unique có thể bị từ chối.
- Unique compound index gồm shard key làm prefix **không** thay thế yêu cầu unique **trên chính shard key** khi `sh.shardCollection(...,true)`.
- Nếu collection chứa duplicate shard key values, unique index build sẽ thất bại.

Không sử dụng `unique:true` cho shard key khi collection phải có **nhiều document trên một giá trị shard key**. Ví dụ unique `{tenantId:1}` sẽ khiến tenant chỉ được có một document, trái yêu cầu thông thường.

## 11. Kiểm chứng giới hạn _id trên sharded collection

Collection `usersByTenant` sharded theo `tenantId` vẫn có index:

~~~javascript
db.usersByTenant.getIndexes();
~~~

Mặc dù `_id_` là unique, vì shard key **không** phải `_id`, default index không tự bảo đảm global uniqueness.

### 11.1. Hai document trùng _id có thể xảy ra

~~~javascript
// Chỉ minh họa một rủi ro; kết quả phụ thuộc chunk placement.
db.usersByTenant.insertOne({
  _id: "cross-shard-duplicate",
  tenantId: "tenant-A",
  emailKey: "one@example.test"
});

db.usersByTenant.insertOne({
  _id: "cross-shard-duplicate",
  tenantId: "tenant-B",
  emailKey: "two@example.test"
});
~~~

- Nếu hai documents vào **cùng shard**, local `_id` unique index từ chối lệnh thứ hai.
- Nếu vào **hai shards khác nhau**, có thể không có constraint global ngăn hai `_id` giống nhau.

Không cần ép balancer hay chuyển chunk trong môi trường dùng chung chỉ để chứng minh điều này.

### 11.2. Không chỉ là vấn đề lý thuyết

Nếu duplicate `_id` đã tồn tại xuyên shard, chúng có thể gây vấn đề khi:

- Query chỉ theo `_id` và ứng dụng kỳ vọng một kết quả duy nhất.
- Data migration/import/export.
- Chunk migration đưa hai khóa trùng về một shard.
- Resharding theo shard key mới.
- Tái xây dựng các tham chiếu theo ID.

Phát hiện và giải quyết duplicate cần runbook có đối soát các references, không chỉ delete bừa một document.

## 12. Hashed shard key và uniqueness

Hashed sharding phân phối document theo giá trị băm của một field:

~~~javascript
sh.shardCollection(
  "sharding_unique_lab.events",
  { eventId: "hashed" }
);
~~~

**Hashing phục vụ phân phối, không phải unique constraint.**

MongoDB **không cho unique hashed index**:

~~~javascript
// Không hợp lệ:
db.events.createIndex(
  { eventId: "hashed" },
  { unique: true }
);
~~~

Cũng không dùng:

~~~javascript
// Không hợp lệ: unique=true trên hashed shard key.
sh.shardCollection(
  "sharding_unique_lab.events",
  { eventId: "hashed" },
  true
);
~~~

### 12.1. Nếu vẫn cần một global unique business key

Đừng chỉ chọn hashed shard key rồi cho rằng cơ sở dữ liệu bảo đảm unique. Hãy cân nhắc shard key ranged theo unique key, hoặc proxy collection/registry.

### 12.2. Không khái quát quá mức

Điều được khẳng định ở đây là **hashed indexes không hỗ trợ unique** và unique shard key dạng hashed bị hạn chế. Các dạng index khác trên collection hashed-sharded còn có quy tắc riêng theo key pattern và phiên bản MongoDB; phải kiểm tra tài liệu trước khi thiết kế.

### 12.3. Ranged key cũng cần xét hotspot

Shard theo `{_id:1}` hoặc `{orderNo:1}` dạng tăng tuần tự có thể dồn write vào vùng dữ liệu mới nhất. Unique correctness là cần thiết, nhưng không thay đánh giá phân bố write và khả năng scale.

## 13. Collation và canonical business key

Hai chuỗi:

~~~text
Lan@Example.Test
lan@example.test
~~~

có thể được coi là cùng một email theo chính sách của ứng dụng, nhưng MongoDB không mặc nhiên chuẩn hóa mọi chuỗi khi tạo index.

### 13.1. Collation trong sharded unique indexes

Theo MongoDB Manual về uniqueness trong sharded clusters, uniqueness trên index key có collation chỉ được bảo đảm khi cấu hình collation là **simple** theo điều kiện tài liệu mô tả. Không coi một unique index có locale-specific case-insensitive collation là giải pháp mặc định cho global unique across shards.

### 13.2. Tạo khóa đã chuẩn hóa

Lưu hai field:

~~~javascript
{
  tenantId: "tenant-A",
  emailDisplay: "Lan@Example.Test",
  emailKey: "lan@example.test"
}
~~~

và index:

~~~javascript
db.usersByTenant.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

`emailDisplay` dùng để hiển thị; `emailKey` là canonical key được tạo theo chính sách nhất quán.

### 13.3. Không coi toLowerCase là đủ cho mọi tình huống

Quy tắc chuẩn hóa có thể cần:

- Trim khoảng trắng đầu/cuối.
- Unicode normalization.
- Case folding theo ngôn ngữ/chuẩn áp dụng.
- Xử lý domain quốc tế.
- Quy tắc email local-part của sản phẩm.
- Kiểm tra giá trị hợp lệ.
- Quy trình nâng cấp khóa canonical khi policy đổi.

Với username tiếng Việt có dấu hoặc Unicode phức tạp, không chỉ gọi lowercase rồi cho rằng mọi chuỗi nhìn giống nhau trở thành cùng bytes.

### 13.4. Mọi writer phải dùng cùng policy

Nếu service A lưu `Lan@Example.Test` thành `lan@example.test`, còn service B lưu nguyên văn làm key, unique index chỉ kiểm tra các giá trị thực đã ghi. Cần một quy tắc canonical hóa thống nhất giữa API, background jobs, migration và import.

## 14. Missing/null và compound unique indexes

Trong unique index, field thiếu được biểu diễn bằng giá trị index tương ứng (thường như null) theo quy tắc MongoDB.

Với:

~~~javascript
{ tenantId: 1, emailKey: 1 }
~~~

insert:

~~~javascript
db.usersByTenant.insertOne({
  _id: "missing-A-1",
  tenantId: "tenant-A",
  displayName: "Chưa có email"
});
~~~

Một document khác ở cùng tenant cũng thiếu `emailKey` có thể bị E11000 vì tổ hợp key chứa cùng `tenant-A` và null/missing.

~~~javascript
try {
  db.usersByTenant.insertOne({
    _id: "missing-A-2",
    tenantId: "tenant-A",
    displayName: "Cũng chưa có email"
  });
} catch (e) {
  print(e.message);
}
~~~

Ngược lại, tenant-B thiếu emailKey có tổ hợp khác nhờ tenantId khác.

### 14.1. Nếu emailKey là bắt buộc

Dùng schema validation, kiểm tra API và ràng buộc dữ liệu để yêu cầu một chuỗi canonical hợp lệ. Unique index không tự làm một field trở thành required.

### 14.2. Nếu emailKey là optional

Cần thiết kế rõ unique chỉ áp dụng cho những document có email hay cả null/missing. Có thể nghiên cứu partial unique index theo giới hạn của sharded collection và phiên bản server, hoặc tách document/collection theo nghiệp vụ.

Không tự khẳng định mọi partial index đều được phép trên shard key hoặc rằng `sparse:true` giải quyết hết các trường hợp null.

## 15. Unique theo tenant khác unique toàn cụm

Giả sử yêu cầu là:

~~~text
tenant-A được có email x@example.test một lần.
tenant-B cũng được có email x@example.test một lần.
~~~

Unique `{tenantId:1,emailKey:1}` đáp ứng.

Nhưng nếu sản phẩm đổi yêu cầu:

~~~text
Email x@example.test chỉ được sử dụng một lần
trong toàn bộ hệ thống, bất kể tenant.
~~~

cùng index **không đáp ứng** vì `tenantId` khác nhau cho ra unique key khác nhau.

### 15.1. Hai giải pháp chính

**Giải pháp A — Chọn chính emailKey làm range shard key.**

~~~javascript
shardKey = { emailKey: 1 };
uniqueIndex = { emailKey: 1 };
~~~

Điều này giúp enforce unique email trực tiếp, nhưng phải kiểm tra cardinality, hotspot, query by tenant và khả năng thay đổi email.

**Giải pháp B — Dùng proxy collection global unique.**

Giữ users shard theo tenantId, còn collection proxy lưu khóa email global và được dùng trong transaction khi tạo user.

Giải pháp B thường phù hợp nếu yêu cầu phân bố/query theo tenant quan trọng hơn việc shard collection chính theo email.

### 15.2. Không lẫn unique toàn collection với xuyên nhiều collections

Unique index trên một `users` collection không kiểm tra `admins` hay `invitedUsers` ở collection khác. Nếu email phải unique trên **toàn identity system**, hãy xác định một registry/source of truth chung cho mọi luồng đăng ký.

## 16. Proxy collection: bảo đảm unique khi field không phải shard key

MongoDB Manual gợi ý **proxy collection** cho field cần unique nhưng không thể đưa vào shard key của collection chính.

Sơ đồ:

~~~text
                    Create user request
                            |
                            v
                      MongoDB transaction
                        /           \
                       v             v
                emailClaims       usersByTenant
                unique email      shard tenantId
                       \             /
                        \           /
                        commit hoặc abort
~~~

Collection chính:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-A",
  emailKey: "lan@example.test",
  displayName: "Lan"
}
~~~

Collection proxy có thể dùng emailKey làm `_id`:

~~~javascript
{
  _id: "lan@example.test",
  userId: ObjectId("..."),
  tenantId: "tenant-A"
}
~~~

Nếu proxy **không sharded**, default unique `_id` index bảo đảm không thể insert hai claims cùng email vào collection proxy.

### 16.1. Tạo proxy

~~~javascript
use sharding_unique_lab
db.createCollection("emailClaims");
~~~

Trong bài demo, không shard proxy. Nếu muốn shard proxy khi quy mô tăng, phải đánh giá shard key phù hợp với uniqueness, ví dụ range shard theo chính emailKey và unique index tương ứng.

### 16.2. Vì sao cần transaction?

Nếu ghi proxy trước nhưng insert user thất bại, email bị chiếm mà user không được tạo. Nếu user được tạo trước nhưng proxy thất bại, user không được kiểm soát unique global.

Transaction đưa hai thao tác vào **cùng đơn vị commit/abort**, ngăn tình trạng hai collections lệch nhau do một bước thất bại.

### 16.3. Transaction mongosh minh họa

~~~javascript
function createUserGlobal(
  tenantId,
  emailKey,
  displayName
) {
  const s = db.getMongo().startSession({
    readPreference: { mode: "primary" }
  });

  const d = s.getDatabase("sharding_unique_lab");
  const userId = new ObjectId();

  try {
    s.startTransaction({
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });

    // Claim email global.
    d.emailClaims.insertOne({
      _id: emailKey,
      tenantId: tenantId,
      userId: userId
    });

    // Tạo user trong sharded collection.
    d.usersByTenant.insertOne({
      _id: userId,
      tenantId: tenantId,
      emailKey: emailKey,
      displayName: displayName
    });

    s.commitTransaction();
    return userId;
  } catch (e) {
    try { s.abortTransaction(); } catch (_) {}
    throw e;
  } finally {
    s.endSession();
  }
}
~~~

Giả định cả hai collections đã tồn tại và cluster hỗ trợ multi-document transactions. Đây là **mẫu giảng giải**, chưa phải bộ xử lý production với retry đầy đủ.

### 16.4. Thử hai tenant cùng email

~~~javascript
createUserGlobal(
  "tenant-A",
  "unique-global@example.test",
  "Lan"
);

try {
  createUserGlobal(
    "tenant-B",
    "unique-global@example.test",
    "Minh"
  );
} catch (e) {
  print("Global duplicate prevented: " + e.message);
}
~~~

Request thứ hai bị chặn tại `emailClaims` do unique `_id`. Không cần biết document user sẽ nằm trên shard A hay B.

### 16.5. Không dùng hai insert rời rạc nếu cần atomicity

~~~javascript
// Không bảo đảm nguyên tử giữa hai collections:
db.emailClaims.insertOne({ _id: emailKey, userId });
db.usersByTenant.insertOne({ _id: userId, tenantId, emailKey });
~~~

Nếu process chết ở giữa, hai collection có thể không còn tương ứng.

Nếu không thể dùng transaction, phải thiết kế một quy trình reservation, TTL, status, reconciliation và compensation rõ ràng. Không coi hai lệnh tách rời là tương đương transaction.

## 17. Check-then-insert không bảo vệ trước race

Cách dễ sai:

~~~javascript
const exists = db.usersByTenant.findOne({
  emailKey: "taken@example.test"
});

if (!exists) {
  db.usersByTenant.insertOne({
    tenantId: "tenant-A",
    emailKey: "taken@example.test"
  });
}
~~~

Timeline:

~~~text
Client A                      Client B
   |                             |
   | find(email) -> chưa có       |
   |                             | find(email) -> chưa có
   |                             |
   | insert(email)               | insert(email)
   |                             |
   +-------- cả hai có thể thử ghi
~~~

Đọc trước rồi ghi sau là hai hành động khác nhau. Không có ràng buộc chung, hai clients có thể cùng qua bước kiểm tra.

### 17.1. Snapshot isolation có giải quyết không?

Chỉ mở hai snapshot transactions để cả hai đọc “email chưa có” không đủ nếu hai transaction insert vào **hai document khác nhau** mà không tranh chấp một unique key.

Unique index ở proxy tạo điểm tranh chấp thực sự: chỉ một request có thể chiếm cùng emailKey.

### 17.2. Duplicate key là một kết quả hợp lệ của cạnh tranh

Khi hai request cùng tạo email global, một request có thể commit, request khác nhận E11000. Đó là cơ chế bảo vệ nghiệp vụ, không nhất thiết là lỗi hệ thống.

Tầng API có thể map lỗi đó thành HTTP 409 Conflict hoặc kết quả validation tương đương.

### 17.3. Idempotency vẫn cần thiết

Nếu client timeout sau commit nhưng không nhận ACK, lần retry có thể gặp duplicate key. Không được tự coi mọi E11000 là success; cần đối chiếu requestId, owner và payload để phân biệt request đã thành công với email bị chiếm bởi một request khác.

## 18. Đổi email hoặc xóa user khi dùng proxy

### 18.1. Đổi email

Một quy trình transaction:

1. Tính `newEmailKey` bằng cùng canonicalization policy.
2. Insert claim mới với unique key.
3. Update user document theo shard key và userId.
4. Delete claim cũ, nhưng kiểm tra `userId`/owner để không xóa claim của người khác.
5. Commit với write concern phù hợp.

Nếu bước 2 vi phạm unique, transaction abort và user giữ email cũ.

### 18.2. Xóa user

Nếu policy cho phép email được tái sử dụng sau xóa:

~~~text
Transaction:
  delete user đúng tenant + userId
  delete claim đúng emailKey + userId
  commit
~~~

Nếu policy giữ email sau soft-delete, proxy có thể giữ claim với trạng thái tương ứng. Đây là quyết định nghiệp vụ, không phải quy tắc unique index tự động.

### 18.3. Không xóa claim chỉ theo email trong workflow có race

Nên xác nhận email claim thuộc user đang được sửa/xóa. Nếu không, một request đến trễ có thể xóa reservation của một owner khác sau khi đã có thay đổi quyền sở hữu.

## 19. Tạo sharded collection khi đã có unique indexes

Giả sử collection `users` chưa shard:

~~~javascript
db.users.createIndex(
  { emailKey: 1 },
  { unique: true }
);

db.users.createIndex(
  { usernameKey: 1 },
  { unique: true }
);
~~~

Muốn shard theo:

~~~javascript
{ tenantId: 1 }
~~~

`sh.shardCollection` có thể từ chối vì các unique indexes cũ không có `tenantId` làm prefix.

### 19.1. Không chỉ thêm index mới rồi coi vấn đề biến mất

Ngay cả khi thêm:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

những indexes unique cũ `{emailKey:1}` và `{usernameKey:1}` vẫn không tương thích với shard key mới.

### 19.2. Quyết định migration theo yêu cầu sản phẩm

Nếu email/username phải unique toàn hệ thống, đừng tùy tiện drop global indexes rồi thay bằng tenant-scoped indexes.

Có thể:

- Chọn shard key đáp ứng một global unique field.
- Chuyển các global unique fields khác sang proxy registries.
- Tách identity registry khỏi tenant profiles.
- Tổ chức phased migration bảo đảm tất cả writers tuân thủ ràng buộc mới.

### 19.3. Checklist migration

1. Kiểm kê unique indexes của collection hiện có.
2. Chốt scope global/tenant cho từng business key.
3. Chốt policy canonicalization và dữ liệu missing/null.
4. Dò duplicates trước khi tạo index mới.
5. Lập kế hoạch thay indexes và shard key.
6. Xác định cách ngăn concurrent writes phá invariant trong quá trình chuyển.
7. Chạy staging trên dữ liệu đại diện.
8. Chỉ thực hiện DDL trên production với runbook và giám sát.
9. Kiểm tra data integrity sau migration.
10. Không drop ràng buộc quan trọng khi chưa có bảo đảm thay thế.

## 20. Resharding và unique constraints hiện có

Resharding thay đổi shard key của một collection, nên thay đổi cả điều kiện của unique indexes.

Ví dụ ban đầu:

~~~javascript
oldShardKey = { tenantId: 1 };
uniqueIndex = { tenantId: 1, emailKey: 1 };
~~~

Muốn đổi thành:

~~~javascript
newShardKey = { regionId: 1 };
~~~

Unique index cũ không có `regionId` làm prefix. MongoDB yêu cầu shard key mới thỏa các yêu cầu unique index hiện có, nên phương án reshard này có thể bị từ chối.

### 20.1. Duplicate _id ảnh hưởng resharding

MongoDB Manual nêu resharding có thể **thất bại khi `_id` values không global unique**, để tránh hỏng dữ liệu. Duplicate `_id` cũng có thể cản trở chunk migration.

Điều này là hệ quả vận hành thực tế của ngoại lệ default `_id` unique per shard.

### 20.2. Không “cứ reshard rồi xử lý duplicates sau”

Trước khi reshard:

- Xác định tất cả unique indexes.
- Kiểm tra khóa _id global của các document hiện có.
- Xem shard key mới có được làm prefix của những unique indexes cần giữ không.
- Đánh giá tham chiếu ID từ collections/services khác.
- Có kế hoạch xử lý duplicate và rollback/maintenance.

### 20.3. Thay shard key không chỉ để làm một index hợp lệ

Shard key ảnh hưởng query targeting, khả năng phân phối write và balancing. Việc đổi shard key chỉ để hợp một unique index có thể tạo hotspot hoặc scatter-gather lớn.

## 21. Chunk migration không làm mất nguyên tắc unique

Chunks có thể di chuyển giữa shards để cân bằng dữ liệu. Một unique index đúng prefix được thiết kế sao cho ràng buộc vẫn có ý nghĩa khi định tuyến/chunk ownership thay đổi.

Nhưng duplicate `_id` đã tồn tại ở hai shards là vấn đề khác: khi chunks được di chuyển khiến những document trùng `_id` gặp nhau trên một shard, có thể phát sinh xung đột.

**Không chủ động tạo duplicate _id hoặc ép chunk migrations trên cluster production** chỉ để thử nghiệm. Khi phát hiện duplicate, cần sửa dữ liệu theo quy trình có đối chiếu references.

### 21.1. Metadata và index consistency

Trên một sharded cluster, việc xây index hoặc thay topology cần được theo dõi trên toàn cluster. Không suy luận từ `getIndexes()` của một shard riêng lẻ rằng mọi shard đều ở trạng thái giống nhau.

Sử dụng công cụ kiểm tra metadata/index consistency được phiên bản MongoDB của tổ chức hỗ trợ.

## 22. Mongosh: xem shard key và unique indexes

### 22.1. Xem sharding status

~~~javascript
sh.status();
~~~

Tìm namespace:

~~~text
sharding_unique_lab.usersByTenant
~~~

Xác định shard key thực tế, không suy đoán theo tên collection.

### 22.2. Xem index definitions

~~~javascript
db.usersByTenant.getIndexes();
~~~

Một kết quả minh họa:

~~~javascript
[
  {
    key: { _id: 1 },
    name: "_id_",
    unique: true
  },
  {
    key: { tenantId: 1 },
    name: "idx_tenant"
  },
  {
    key: { tenantId: 1, emailKey: 1 },
    name: "uniq_tenant_email",
    unique: true
  }
]
~~~

Nếu shard key là `{tenantId:1}`:

- `_id_`: local uniqueness, không chứng minh global.
- `idx_tenant`: index thường.
- `uniq_tenant_email`: unique cặp tenant/email, có prefix hợp lệ.

### 22.3. Vì sao chỉ xem unique:true là chưa đủ?

Giá trị `unique:true` là thuộc tính index. Để biết **phạm vi global** trong sharded collection, phải kết hợp nó với shard key pattern và những ngoại lệ MongoDB quy định.

## 23. Xử lý E11000 duplicate key

MongoDB thường trả error code **11000** khi unique index bị vi phạm:

~~~javascript
try {
  db.usersByTenant.insertOne({
    _id: new ObjectId(),
    tenantId: "tenant-A",
    emailKey: "lan@example.test"
  });
} catch (e) {
  if (e.code === 11000) {
    print("Duplicate key");
  } else {
    throw e;
  }
}
~~~

### 23.1. Một collection có thể có nhiều unique indexes

E11000 có thể đến từ:

- `_id_` local uniqueness.
- `uniq_tenant_email`.
- Unique index khác.
- Proxy emailClaims `_id_`.

Không trả mặc định “email đã tồn tại” cho mọi E11000. Trong ứng dụng thật, xác định index/key vi phạm và đối chiếu hợp đồng nghiệp vụ.

### 23.2. Duplicate key khác lỗi mạng

- Duplicate key: ràng buộc dữ liệu bị vi phạm.
- Network timeout: client có thể chưa nhận kết quả cuối.
- Transaction transient error: có thể retry theo protocol.
- Commit unknown: transaction có thể đã commit, cần retry commit hoặc đối soát.

Không retry vô hạn một duplicate key thực sự, cũng không xem mọi timeout là bằng chứng write chưa thực hiện.

### 23.3. RequestId và idempotency

Dùng ID request ổn định, canonical business key và khả năng tra cứu kết quả để xác nhận một request đã được thực hiện trước đó hay không.

Ví dụ retry tạo user với email đã bị claim:

1. Tìm claim theo emailKey.
2. Kiểm tra userId và requestId/payloadHash.
3. Nếu là chính request đã hoàn tất, trả kết quả cũ phù hợp.
4. Nếu thuộc request khác, trả conflict.
5. Không tự đổi userId ở mọi lần retry khiến nghiệp vụ có nhiều account.

## 24. Java Sync Driver: tạo index đúng prefix

Giả định `database` là `MongoDatabase` của sharded cluster, và collection đã shard theo `{tenantId:1}`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

MongoCollection<Document> users =
    database.getCollection("usersByTenant");

String indexName = users.createIndex(
    Indexes.ascending("tenantId", "emailKey"),
    new IndexOptions()
        .name("uniq_tenant_email")
        .unique(true)
);

System.out.println(indexName);
~~~

Cần kiểm tra index không đã tồn tại với cấu hình khác trước khi dùng code migration trên production.

### 24.1. Chèn và xử lý duplicate

~~~java
import com.mongodb.MongoWriteException;
import org.bson.Document;
import org.bson.types.ObjectId;

Document user = new Document("_id", new ObjectId())
    .append("tenantId", "tenant-A")
    .append("emailKey", "lan@example.test")
    .append("displayName", "Lan");

try {
    users.insertOne(user);
    System.out.println("User created");
} catch (MongoWriteException ex) {
    if (ex.getError().getCode() == 11000) {
        System.out.println("Duplicate key, inspect index");
    } else {
        throw ex;
    }
}
~~~

### 24.2. Kết nối qua mongos/cluster URI

Driver phải dùng URI đúng sharded cluster. Đừng kết nối trực tiếp vào shard primary để ghi như thể đó là toàn bộ collection sharded; cần routing qua mongos và chính sách của deployment.

## 25. Java transaction với proxy collection

Giả định:

- `usersByTenant` là collection chính sharded theo tenantId.
- `emailClaims` là collection proxy unsharded với unique `_id`.
- Cả hai collections đã tồn tại.
- `client` là `MongoClient`, `database` là `MongoDatabase`.

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.ObjectId;

MongoCollection<Document> claims =
    database.getCollection("emailClaims");
MongoCollection<Document> users =
    database.getCollection("usersByTenant");

TransactionOptions opts = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

ObjectId userId = new ObjectId();
String tenantId = "tenant-A";
String emailKey = "global-new@example.test";

try (ClientSession session = client.startSession()) {
    session.startTransaction(opts);

    try {
        claims.insertOne(
            session,
            new Document("_id", emailKey)
                .append("tenantId", tenantId)
                .append("userId", userId)
        );

        users.insertOne(
            session,
            new Document("_id", userId)
                .append("tenantId", tenantId)
                .append("emailKey", emailKey)
                .append("displayName", "New User")
        );

        session.commitTransaction();
    } catch (Exception e) {
        try {
            session.abortTransaction();
        } catch (Exception ignored) {}
        throw e;
    }
}
~~~

Đây là ví dụ kỹ thuật tối giản; production cần transaction retry pattern cho `TransientTransactionError` và `UnknownTransactionCommitResult`, deadlines, idempotency và quản lý side effects ngoài database.

### 25.1. Vì sao không chỉ có transaction mà bỏ proxy unique?

Nếu hai transaction cùng đọc “email chưa có”, rồi insert hai users khác nhau trên hai shards, chúng không bắt buộc xung đột nếu không có unique key chung. Unique `_id` trong proxy tạo một điểm tranh chấp rõ ràng.

### 25.2. Tạo ObjectId một lần cho request nghiệp vụ

Trong transaction helper có thể retry, phải có chính sách giữ request identity và đối soát kết quả. Không tạo một tài khoản mới độc lập cho mỗi lần retry mà không biết lần trước đã commit hay chưa.

## 26. Schema validation, null và dữ liệu biên

Unique index không thay thế schema validation.

Nếu `emailKey` là field bắt buộc, validation cần yêu cầu nó có đúng kiểu và định dạng theo policy. Unique index chỉ kiểm tra hai document có cùng key tương ứng hay không.

Ví dụ hai document thiếu emailKey cùng tenant có thể trùng key dạng `(tenant-A,null)` trong unique compound index.

Nếu email optional, cần thiết kế riêng:

- Có cho nhiều users chưa có email trong cùng tenant không?
- Có cần partial unique index, và nó có đáp ứng giới hạn sharded collection không?
- Có nên lưu email ở một collection con riêng?
- Có nên có trạng thái `emailVerified` trước khi claim email không?
- Cần giải phóng claim khi user soft-delete không?

Không nên dựa vào hành vi mặc định của null/missing mà chưa kiểm tra.

### 26.1. Schema đặc thù multi tenant

Một user nên có:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-A",
  emailKey: "lan@example.test",
  displayName: "Lan"
}
~~~

Filter API vẫn phải gắn tenantId từ phiên xác thực. Unique index không phải một chính sách authorization.

## 27. Đánh đổi giữa correctness và hiệu năng

| Thiết kế | Ưu điểm | Rủi ro |
|---|---|---|
| Shard theo tenantId | Truy vấn theo tenant dễ target; unique tenant-scoped tự nhiên | Tenant rất lớn có thể tạo hotspot |
| Shard theo emailKey | Unique email global trực tiếp, lookup email dễ target | Query theo tenant có thể scatter-gather |
| Shard theo hashed key | Phân bố write tốt cho khóa tăng tuần tự | Hashed index không dùng unique constraint như range key |
| Proxy global unique | Giữ shard key chính theo workload nhưng vẫn claim global | Thêm collection, transaction, tải registry và quy trình cleanup |
| ID ObjectId ngẫu nhiên phân tán | Xác suất ID trùng rất thấp | Không phải bằng chứng global unique theo constraint nếu shard key khác |
| Unique compound theo shard-key prefix | Constraint được MongoDB enforce trên collection | Scope chỉ là tổ hợp field, không phải từng field |

### 27.1. Index unique cũng có chi phí ghi

Unique index cần cập nhật, kiểm tra conflict và tiêu thụ storage/I/O. Thêm nhiều unique indexes có thể làm write latency tăng và ảnh hưởng migration.

### 27.2. Tối ưu query không chỉ là thêm unique index

Index key phải phục vụ filter/sort. Một index chỉ dùng để giữ uniqueness có thể không tối ưu cho mọi truy vấn.

Nếu collection shard theo tenantId, API tìm user qua email nên dùng:

~~~javascript
db.usersByTenant.findOne({
  tenantId: "tenant-A",
  emailKey: "lan@example.test"
});
~~~

Thao tác không có tenantId có thể yêu cầu nhiều shards, dù có index local theo email.

## 28. Sai lầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “_id luôn unique global” | Default _id index có thể chỉ unique per-shard |
| “Unique:true trên field nào cũng được” | Sharded collection yêu cầu full shard-key prefix, trừ ngoại lệ _id |
| “Có shard key trong index là đủ” | Phải đúng prefix và thứ tự |
| “Unique tenantId+email nghĩa là email unique global” | Nó unique trên cặp |
| “Hai tenant khác nhau chắc chắn ở hai shards” | Không; phụ thuộc chunk placement |
| “Hashed shard key có thể unique:true” | Không hỗ trợ unique hashed index |
| “ObjectId bảo đảm tuyệt đối không bao giờ trùng” | Xác suất thấp, không thay constraint |
| “Đã có snapshot transaction nên khỏi cần unique index” | Check-then-insert vẫn có race nếu không tranh cùng key |
| “E11000 luôn là email trùng” | Có thể do _id hoặc index khác |
| “Drop unique index cũ là cách shard nhanh” | Có thể phá ràng buộc nghiệp vụ |
| “Reshard không liên quan unique indexes” | New shard key phải tương thích unique constraints |
| “Đã dùng proxy thì có thể ghi hai collection riêng” | Cần transaction hoặc cơ chế đồng bộ rõ |
| “Giá trị null không tính trong unique” | Missing/null có semantics index key cần xét |
| “Một query có _id trả một record” | Không bảo đảm nếu _id trùng xuyên shards |
| “Chỉ cần sửa app, không cần dọn dữ liệu cũ” | Duplicate existing data vẫn cản migration và index build |

## 29. Bài tập thực hành

Chạy các bài DDL/ghi trên **sharded cluster thử nghiệm**, không trên production. Nếu không có cluster, hãy phân tích kết quả dựa trên quy tắc đã học.

### Bài 1 — Xác định unique indexes hợp lệ

Shard key `{tenantId:1}`. Phân loại:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, emailKey: 1 }
{ emailKey: 1 }
{ emailKey: 1, tenantId: 1 }
{ _id: 1 }
~~~

Giải thích ngoại lệ của `_id`.

### Bài 2 — Compound shard key

Với shard key:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

Chỉ ra index nào có prefix đúng:

~~~javascript
{ tenantId: 1, regionId: 1, orderNo: 1 }
{ tenantId: 1, orderNo: 1, regionId: 1 }
{ regionId: 1, tenantId: 1, orderNo: 1 }
{ tenantId: 1, orderNo: 1 }
~~~

### Bài 3 — Tạo unique theo tenant

Tạo unique `{tenantId:1,emailKey:1}` trên collection đã shard theo tenantId. Insert hai document cùng email ở hai tenants, sau đó hai document cùng email trong một tenant.

**Kỳ vọng:** Chỉ trường hợp thứ hai bị từ chối.

### Bài 4 — Unique sai prefix

Thử:

~~~javascript
db.usersByTenant.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

**Hỏi:** Vì sao mongos không thể coi nó là global unique constraint?

### Bài 5 — _id qua hai shards

Giả sử collection shard theo `{tenantId:1}`, hai documents có cùng _id nhưng tenant khác nhau.

**Hỏi:** Nếu chúng ở cùng shard thì điều gì xảy ra? Nếu khác shards thì sao? Tại sao không được dựa vào vị trí hiện tại để thiết kế invariant?

### Bài 6 — ObjectId

Ứng dụng dùng `new ObjectId()` cho mọi user. Giải thích lợi ích và giới hạn so với một database-enforced global constraint.

### Bài 7 — Unique shard key

Tạo range-sharded collection `licenseCodes` với unique `licenseCode`. Vì sao không nên thay shard key thành hashed rồi vẫn giữ `unique:true`?

### Bài 8 — Canonicalization

Hai email:

~~~text
Lan@Example.Test
lan@example.test
~~~

Đề xuất canonicalization policy nhất quán và unique key cho tenant. Vì sao không nên tùy tiện dùng collation non-simple trên sharded unique index?

### Bài 9 — Null/missing

Với unique `{tenantId:1,emailKey:1}`, hai document tenant-A đều thiếu emailKey.

**Hỏi:** Vì sao bị xem trùng theo index key? Có khác gì nếu một document thuộc tenant-B?

### Bài 10 — Unique global email

Chọn hai phương án khả thi:

A. Shard user theo tenantId, unique index emailKey trực tiếp.

B. Shard user theo emailKey và unique index emailKey.

C. Shard user theo tenantId, dùng proxy emailClaims unique và transaction.

**Đáp án:** B hoặc C tùy workload; A không đáp ứng điều kiện của sharded unique index.

### Bài 11 — Proxy + transaction

Trình bày các bước reserve claim email, insert user và commit. Nếu insert user thất bại sau khi claim được tạo, transaction giải quyết thế nào?

### Bài 12 — Concurrent inserts

Hai requests chạy `findOne(email)` rồi `insertOne` gần như đồng thời. Tại sao cả hai có thể qua findOne? Unique index hoặc proxy giải quyết ở bước nào?

### Bài 13 — E11000 và API

Một insert user nhận E11000 nhưng không biết index nào. Tại sao không nên trả “email đã tồn tại” ngay? Phân biệt duplicate ID với duplicate business key.

### Bài 14 — Retry sau timeout

Request A commit user thành công nhưng không nhận ACK; request retry gặp duplicate email claim.

**Hỏi:** Làm sao xác minh claim hiện có thuộc request A thay vì người khác?

### Bài 15 — Migration indexes

Unsharded collection có unique `emailKey`, `usernameKey`. Muốn shard theo tenantId.

**Hỏi:** Vì sao `shardCollection` có thể từ chối? Đưa ra phương án bảo toàn global uniqueness.

### Bài 16 — Resharding

Collection có unique `{tenantId:1,emailKey:1}`, muốn reshard sang `{regionId:1}`.

**Hỏi:** Ràng buộc nào bị vi phạm? Cần chuẩn bị dữ liệu và indexes ra sao?

### Bài 17 — Chunk migration và duplicate _id

Nếu dữ liệu có duplicate `_id` ở hai shards, vì sao chunk migration hoặc resharding có thể gặp lỗi? Có được xóa ngẫu nhiên một document không?

### Bài 18 — Thiết kế multi tenant

Yêu cầu:

~~~text
username unique theo tenant
email unique toàn hệ thống
orderNo unique theo tenant
~~~

Chọn shard keys, compound indexes và proxy collections phù hợp. Phân biệt semantics từng constraint.

### Bài 19 — Quan sát metadata

Chạy:

~~~javascript
sh.status();
db.usersByTenant.getIndexes();
~~~

Tìm shard key thực tế, những index có unique:true, những index có full shard key prefix và ý nghĩa `_id_`.

### Bài 20 — Đánh đổi hiệu năng

So sánh ba phương án:

1. Shard users theo tenantId.
2. Shard users theo emailKey.
3. Shard users theo tenantId + proxy global.

Nêu tác động tới routing, throughput, khả năng unique email và độ phức tạp transaction.

## 30. Checklist trước khi triển khai production

### Về tính đúng đắn

- [ ] Scope uniqueness đã được định nghĩa: tenant, collection hay toàn hệ thống.
- [ ] Đã kiểm tra shard key thực tế.
- [ ] Unique index có toàn bộ shard key làm prefix.
- [ ] Không dùng default _id local uniqueness như một bảo đảm global không có cơ sở.
- [ ] Không tạo unique hashed index.
- [ ] Hiểu cặp/triple compound unique khác unique từng field.
- [ ] Có chính sách xử lý missing/null.
- [ ] Có canonicalization policy thống nhất.
- [ ] Có kiểm tra concurrent insert/update.
- [ ] Có proxy registry nếu cần global unique ngoài shard key.

### Về vận hành

- [ ] Kết nối qua mongos và dùng quyền quản trị đúng.
- [ ] Kiểm kê unique indexes trước khi shard/reshard.
- [ ] Đã kiểm tra duplicate dữ liệu cũ, đặc biệt _id.
- [ ] Không drop unique constraints khi chưa có thay thế.
- [ ] Có runbook index build và kiểm tra consistency trên các shards.
- [ ] Có kế hoạch xử lý chunk migration khi phát hiện duplicates.
- [ ] Có giám sát E11000 và transaction errors.
- [ ] Có idempotency khi client retry.
- [ ] Có thiết kế cập nhật/xóa email claims.
- [ ] Có đánh giá bottleneck của proxy collection.

### Về hiệu năng và an toàn

- [ ] Shard key phân bố dữ liệu phù hợp với workload.
- [ ] Không có tenant quá lớn mà chưa xem tác động hotspot.
- [ ] Query đi kèm tenantId/điều kiện authorization phù hợp.
- [ ] Có index cho filter/sort ngoài unique constraints.
- [ ] Đã đo scatter-gather và routing qua mongos.
- [ ] Có giám sát index size và write amplification.
- [ ] Có staging test với dữ liệu đại diện trước DDL production.

## 31. Kết luận

MongoDB Sharding đưa tính duy nhất từ một yêu cầu trên một node thành bài toán **ràng buộc xuyên những vùng dữ liệu phân tán**.

- Với **range sharding**, unique index bình thường phải có **toàn bộ shard key làm prefix**, trừ default `_id` index có giới hạn riêng.
- **`_id` có thể chỉ unique trong từng shard** nếu shard key khác `_id`. Hãy dùng ID generation có kiểm soát, và thêm cơ chế toàn cục nếu nghiệp vụ đòi bảo đảm tuyệt đối.
- **Compound unique** ràng buộc cả tổ hợp. `{tenantId,emailKey}` là unique theo tenant, **không** unique email toàn cluster.
- **Hashed index không hỗ trợ unique constraint**; cân bằng phân phối dữ liệu và uniqueness là hai mục tiêu khác nhau.
- **Global business key ngoài shard key** có thể được quản lý qua proxy collection có unique index và transaction với collection chính.
- **Migrations, resharding và chunk moves** phải tính đến tất cả unique indexes và dữ liệu trùng đã tồn tại.
- **Canonicalization, null handling, concurrent writes và idempotency** là phần không thể thiếu của thiết kế.

Chọn shard key tốt không chỉ giúp đọc/ghi phân tán nhanh, mà còn giúp MongoDB **kiểm chứng được những ràng buộc duy nhất quan trọng nhất của nghiệp vụ**.

## Tài liệu tham khảo chính thức

- [MongoDB Manual — Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/)
- [MongoDB Manual — Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Enforce Uniqueness on the Shard Key Values](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-shard-key-values/)
- [MongoDB Manual — Enforce Uniqueness on a Field That Is Not the Shard Key](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-non-shard-key-field/)
- [MongoDB Manual — Create a Unique Index on Existing Sharded Collection](https://www.mongodb.com/docs/manual/tutorial/create-unique-index-on-sharded-collection/)
- [MongoDB Manual — Sharded Collections with Unique Indexes](https://www.mongodb.com/docs/manual/tutorial/shard-collection-with-unique-index/)
- [MongoDB Manual — Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [MongoDB Manual — Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
