# ObjectId, trường _id và lựa chọn khóa định danh trong MongoDB

## 1. Mục tiêu và bối cảnh

Mỗi document trong một collection MongoDB cần được nhận diện chính xác để ứng dụng có thể tìm, cập nhật, xóa, liên kết dữ liệu hoặc chuyển ID qua API. **Trường _id** đảm nhiệm vai trò khóa định danh của document. **ObjectId** là kiểu BSON thường được MongoDB sử dụng cho giá trị của trường đó. Hai khái niệm liên quan chặt chẽ nhưng không đồng nghĩa: _id là tên trường, còn ObjectId là một loại giá trị có thể chứa trong trường.

Sau bài học này, bạn có thể:

- Giải thích cấu trúc 12 byte và cách hiển thị 24 ký tự hexadecimal của ObjectId.
- Hiểu cách MongoDB gán, lập index, so khớp và bảo vệ giá trị _id.
- Tránh lỗi truy vấn khi một ID được lưu bằng ObjectId nhưng ứng dụng truyền chuỗi.
- Lựa chọn hợp lý giữa ObjectId, UUID, chuỗi nghiệp vụ, số nguyên và khóa tổng hợp.
- Xây dựng bộ dữ liệu nhỏ để quan sát kiểu BSON của _id, kết quả truy vấn và phép liên kết.
- Áp dụng các quy ước định danh vào MongoDB Java Driver và ứng dụng đa tenant.

Ví dụ dùng **mongosh** và database thực hành riêng **mongo_identity_lab**. Nếu chưa có MongoDB và mongosh, cần chuẩn bị MongoDB server chạy cục bộ hoặc môi trường thử nghiệm được cấp quyền tạo collection, insert và index.

## 2. Phân biệt _id, ObjectId và khóa nghiệp vụ

Xét document sản phẩm:

~~~javascript
{
  _id: ObjectId("66f000000000000000000001"),
  sku: "NOTE-A5-001",
  name: "Sổ tay A5",
  price: NumberDecimal("45000.00")
}
~~~

| Thành phần | Vai trò | Có bắt buộc phải dùng? |
| --- | --- | --- |
| **_id** | Khóa định danh của document, dùng để phân biệt với document khác trong collection | Có |
| **ObjectId** | Kiểu BSON 12 byte phù hợp để làm giá trị _id | Không; có thể dùng các loại khóa khác |
| **sku** | Mã hàng theo nghiệp vụ, phục vụ bán hàng hoặc tích hợp kho | Tùy ứng dụng |
| **Unique index trên sku** | Bảo đảm mã SKU không trùng theo phạm vi nghiệp vụ đã chọn | Cần nếu muốn MongoDB thực thi tính duy nhất của SKU |

Nếu một document mới được insert mà không khai báo _id, driver hoặc server sẽ cấp một ObjectId tùy theo đường ghi dữ liệu. Collection MongoDB thông thường có **unique index mặc định trên _id**, vì thế không cần tạo thêm một index _id có cùng định nghĩa.

Tính duy nhất của _id áp dụng trong phạm vi collection, không phải toàn database: hai collection khác nhau có thể dùng cùng một giá trị _id. Riêng ở sharded collection, nếu _id không thuộc vai trò shard key thích hợp, MongoDB chỉ thực thi uniqueness của _id theo từng shard; ứng dụng phải bảo đảm không tạo trùng ID trên các shard. Quyết định shard key và chiến lược ID vì vậy cần xem xét cùng nhau.

MongoDB không tự biết sku, email hay orderNo là khóa duy nhất chỉ vì tên trường của chúng. Quy tắc nghiệp vụ cần được thể hiện bằng unique index tương ứng, ví dụ:

~~~javascript
db.getSiblingDB("mongo_identity_lab")
  .getCollection("lab_products")
  .createIndex(
    { tenantId: 1, sku: 1 },
    { unique: true, name: "ux_tenant_sku" }
  );
~~~

Trong ví dụ này, cùng SKU có thể tồn tại ở các tenant khác nhau, nhưng không được trùng trong cùng một tenant. Việc chọn các trường trong index phải xuất phát từ quy tắc thực tế của miền dữ liệu. Nếu collection được sharding, unique index còn phải tuân theo ràng buộc của shard key.

## 3. ObjectId là kiểu BSON gì?

**ObjectId** có kích thước **12 byte** và thường được biểu diễn trong mongosh bằng **24 ký tự hex** (mỗi byte gồm hai ký tự 0–9 hoặc a–f):

~~~javascript
ObjectId("66f000000000000000000001")
~~~

MongoDB lưu kiểu BSON ObjectId và 12 byte của nó. Phần chữ ObjectId, dấu ngoặc và dấu nháy là cách mongosh hiển thị kiểu dữ liệu, không phải nội dung của một chuỗi được lưu nguyên văn.

### 3.1. Cấu trúc 12 byte

| Vị trí | Số byte | Nội dung | Ý nghĩa |
| --- | ---: | --- | --- |
| 0–3 | 4 | Timestamp tính theo số giây từ Unix epoch | Gợi ý thời gian **sinh ID** |
| 4–8 | 5 | Giá trị ngẫu nhiên thường được khởi tạo theo tiến trình sinh ID | Phân biệt các nguồn tạo ID |
| 9–11 | 3 | Bộ đếm tăng dần, khởi tạo bằng giá trị ngẫu nhiên | Phân biệt các ID tạo liên tiếp |
| **Tổng** | **12** | **24 ký tự hex khi hiển thị** | **Một ObjectId** |

~~~text
ObjectId: 66f00000 1122334455 000001
          | 4 byte | | 5 byte | |3 byte|
          timestamp  ngẫu nhiên  bộ đếm
~~~

Các đoạn byte trong sơ đồ được chọn để dễ quan sát. Phần ngẫu nhiên của ObjectId hiện đại không nên được diễn giải thành địa chỉ IP, mã máy hoặc định danh người dùng.

**Những tính chất quan trọng:**

- ObjectId có xác suất trùng rất thấp khi được tạo đúng cách, nhưng không cung cấp một chứng minh rằng mọi giá trị sinh trong mọi hoàn cảnh đều tuyệt đối duy nhất.
- Bốn byte timestamp khiến ObjectId **thường gần như tăng theo thời gian**, nhưng không bảo đảm thứ tự tuyệt đối khi nhiều tiến trình/máy sinh ID, có lệch đồng hồ hoặc tạo nhiều ID trong cùng một giây.
- Timestamp chỉ có độ chính xác **giây**. ObjectId có thể được tạo trước khi insert, được gán thủ công hoặc được mang sang từ dữ liệu lịch sử.
- ObjectId không phải token bảo mật. Biết một ObjectId không cho phép người dùng bỏ qua xác thực hoặc phân quyền.

### 3.2. Tạo ObjectId và đọc thông tin của nó

Trong mongosh:

~~~javascript
const generatedId = new ObjectId();

print(generatedId);                // Hiển thị ObjectId(...)
print(generatedId.toHexString());  // Chuỗi 24 ký tự hex
print(generatedId.getTimestamp()); // Date suy ra từ timestamp của ObjectId
~~~

Có thể tạo ID cố định để truy vấn ví dụ:

~~~javascript
const fixedId = new ObjectId("66f000000000000000000001");
print(fixedId.toHexString());
print(fixedId.getTimestamp());
~~~

Không dùng **getTimestamp()** làm nguồn thời gian tạo dữ liệu có độ chính xác cao. Nếu ứng dụng cần thời điểm tạo, sửa hoặc ghi nhận nghiệp vụ, lưu riêng **createdAt** và **updatedAt** bằng BSON Date:

~~~javascript
{
  _id: new ObjectId(),
  createdAt: new Date(),
  updatedAt: new Date()
}
~~~

ObjectId giúp nhận diện document; createdAt ghi nhận thời gian theo quy ước ứng dụng. Chúng phục vụ hai mục đích khác nhau.

## 4. Quy tắc vận hành của trường _id

### 4.1. Tính duy nhất, kiểu dữ liệu và tính bất biến

Trường _id của document là khóa định danh. MongoDB cho phép nhiều kiểu BSON làm khóa nhưng **không dùng array hoặc regular expression làm _id**. Thực hành phổ biến dùng một kiểu duy nhất trên toàn collection, thường là ObjectId, String, số nguyên hoặc UUID lưu bằng binary.

Sau khi document đã tồn tại, **_id là bất biến**. Bạn có thể cập nhật các trường nội dung nhưng không thể dùng thao tác update thông thường để biến _id cũ thành một _id mới.

~~~javascript
const lab = db.getSiblingDB("mongo_identity_lab");
const inserted = lab.getCollection("lab_auto_ids").insertOne({
  label: "Document không truyền _id"
});

print(inserted.insertedId);

lab.getCollection("lab_auto_ids").updateOne(
  { _id: inserted.insertedId },
  { $set: { label: "Đã cập nhật" } }
);

// Ví dụ KHÔNG hợp lệ với document đã tồn tại:
// lab.getCollection("lab_auto_ids").updateOne(
//   { _id: inserted.insertedId },
//   { $set: { _id: new ObjectId() } }
// );
~~~

Khi muốn đổi định danh, cần có kế hoạch tạo document mới, chuyển các tham chiếu liên quan và loại bỏ document cũ một cách kiểm soát. Không coi thay _id là thao tác chỉnh sửa trường bình thường.

### 4.2. String và ObjectId là hai giá trị khác kiểu

Hai giá trị dưới đây **không giống nhau**, dù ký tự hiển thị tương tự:

~~~javascript
{ _id: "66f000000000000000000001" }
{ _id: ObjectId("66f000000000000000000001") }
~~~

Document đầu lưu **BSON String**; document sau lưu **BSON ObjectId**. MongoDB so khớp theo cả giá trị và kiểu BSON. Vì vậy:

~~~javascript
const sampleId = inserted.insertedId;
const hex = sampleId.toHexString();

lab.getCollection("lab_auto_ids").findOne({ _id: hex });
// Thông thường null vì truy vấn đang dùng String.

lab.getCollection("lab_auto_ids").findOne({
  _id: new ObjectId(hex)
});
// Tìm đúng document nếu _id trong collection là ObjectId.
~~~

Đây là nguyên nhân phổ biến của lỗi “ID nhìn đúng nhưng findOne trả về null” trong API. Nếu một collection đã chủ động dùng String làm _id, phải giữ kiểu String; không chuyển thành ObjectId chỉ vì chuỗi trông giống 24 ký tự hex.

### 4.3. Chuyển dữ liệu qua JSON

JSON thuần không có kiểu ObjectId. MongoDB dùng **Extended JSON** khi cần biểu diễn rõ loại BSON:

~~~json
{
  "_id": { "$oid": "66f000000000000000000001" },
  "createdAt": { "$date": "2026-01-10T08:00:00Z" }
}
~~~

REST API cũng có thể xuất ID thành chuỗi đơn giản:

~~~json
{
  "id": "66f000000000000000000001",
  "name": "Nguyễn Lan"
}
~~~

Hai biểu diễn mang hợp đồng khác nhau. Extended JSON lưu thông tin kiểu BSON; chuỗi trong API thường dễ tiêu thụ nhưng phải chuyển ngược sang ObjectId ở tầng truy cập database nếu database đang dùng ObjectId. Không mặc định việc parse JSON thông thường sẽ tự tái tạo ObjectId.

### 4.4. Lỗi trùng khóa

Khi insert document có _id đã tồn tại, MongoDB trả lỗi duplicate key, thường mang mã **E11000**. Lỗi này cũng xuất hiện với các unique index khác, ví dụ index duy nhất trên cặp tenantId và email. Vì vậy cần xem tên index trong thông báo lỗi để biết khóa nào thực sự bị trùng.

## 5. Các chiến lược chọn khóa định danh

| Chiến lược | Ưu điểm | Hạn chế | Phù hợp |
| --- | --- | --- | --- |
| **ObjectId** | Gọn, mặc định thuận tiện, sinh từ client, không cần bộ cấp số tập trung | Có timestamp; thứ tự chỉ gần đúng; API cần xử lý kiểu | Phần lớn document CRUD trong MongoDB |
| **UUID BSON Binary subtype 4** | Sinh độc lập, dùng làm định danh xuyên dịch vụ, kích thước nhị phân cố định 16 byte | Phải thống nhất representation giữa các driver | Hệ thống đa dịch vụ và nhiều kho dữ liệu |
| **UUID dưới dạng chuỗi** | Dễ hiển thị và trao đổi dạng văn bản | Dài hơn dạng binary, so khớp khác kiểu với BSON UUID | Tích hợp khi hợp đồng lưu String là chủ đích |
| **Chuỗi nghiệp vụ** | Dễ đọc, có ý nghĩa với người dùng hoặc hệ thống kế thừa | Khó đổi nếu quy tắc nghiệp vụ thay đổi; dễ dài, nhạy cảm với chuẩn hóa | Khóa chắc chắn bất biến, do nguồn chính thức quản lý |
| **Số nguyên tuần tự** | Ngắn, dễ đọc, tương thích hệ thống cũ | Cần cơ chế cấp số không trùng, có thể tạo điểm tập trung và điểm nóng | Hệ thống đã có ID generator đáng tin cậy |
| **Document tổng hợp** | Diễn đạt rõ nhiều thành phần định danh | Cồng kềnh khi query/API/migration, cần thống nhất thứ tự field | Miền dữ liệu có khóa tổng hợp bất biến thực sự |

### 5.1. Giữ ObjectId khi không có lý do mạnh để thay

ObjectId thường là lựa chọn tốt khi dữ liệu chủ yếu nằm trong MongoDB, application không có ID toàn cục sẵn có, và các khóa nghiệp vụ có thể thay đổi.

Ví dụ:

~~~javascript
{
  _id: new ObjectId(),
  tenantId: "t001",
  orderNo: "SO-2026-0001",
  status: "pending",
  createdAt: new Date()
}
~~~

Ở đây **_id** giữ danh tính lâu dài của đơn, còn **orderNo** là số đơn hiển thị cho người dùng. Nếu yêu cầu orderNo duy nhất trong từng tenant, dùng unique index **{ tenantId: 1, orderNo: 1 }**. Cách này cho phép thay quy tắc số đơn mà không cần sửa _id của document.

### 5.2. Khi UUID hữu ích

UUID thường được sinh tại tầng ứng dụng và có thể dùng chung cho MongoDB, event và hệ thống khác. Trong mongosh:

~~~javascript
const uuid = UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479");

lab.getCollection("lab_uuid_examples").insertOne({
  _id: uuid,
  name: "Tài nguyên dùng UUID"
});
~~~

Giá trị trên được lưu dưới dạng BSON UUID Binary subtype 4. Một chuỗi JSON như **"f47ac10b-58cc-4372-a567-0e02b2c3d479"** không có cùng kiểu với BSON binary UUID. Với Java Driver hoặc driver khác, cần thống nhất **UUID representation**; đặc biệt chú ý dữ liệu cũ có thể được tạo theo quy ước byte order khác.

UUID cũng có nhiều phiên bản với tính chất thứ tự khác nhau, chẳng hạn UUID v4 ngẫu nhiên và UUID v7 có cấu trúc thời gian. Không suy ra rằng mọi UUID đều có thứ tự tăng theo thời gian hoặc được MongoDB lập index theo đúng thứ tự nghiệp vụ mong muốn.

### 5.3. Khóa nghiệp vụ có thể thay đổi

Giả sử dùng email làm _id:

~~~javascript
{ _id: "lan@example.test", name: "Nguyễn Lan" }
~~~

Khi khách hàng đổi email, đổi _id sẽ kéo theo việc tạo lại document và sửa các tham chiếu. Ngoài ra, email có thể cần quy tắc chuẩn hóa, bảo vệ dữ liệu cá nhân và phân biệt người dùng theo tenant.

Thiết kế dễ duy trì hơn:

~~~javascript
{
  _id: new ObjectId(),
  tenantId: "t001",
  email: "lan@example.test",
  normalizedEmail: "lan@example.test",
  name: "Nguyễn Lan"
}
~~~

Sau đó tạo index theo phạm vi nghiệp vụ:

~~~javascript
lab.getCollection("lab_users").createIndex(
  { tenantId: 1, normalizedEmail: 1 },
  { unique: true, name: "ux_tenant_normalized_email" }
);
~~~

Quy trình tạo **normalizedEmail** là trách nhiệm của ứng dụng và phải theo chính sách thực tế; việc chỉ chuyển thành chữ thường chưa tự giải quyết mọi quy tắc về email. Khi sharding, phải thiết kế unique index tuân thủ yêu cầu shard key.

### 5.4. Khóa tổng hợp

Một mã hợp đồng có thể chỉ duy nhất trong một tổ chức, ví dụ **(tenantId, contractNo)**. Có hai cách phổ biến:

**Cách A — _id độc lập, unique index cho khóa nghiệp vụ:**

~~~javascript
{
  _id: new ObjectId(),
  tenantId: "t001",
  contractNo: "CT-2026-001"
}
~~~

~~~javascript
lab.getCollection("lab_contracts").createIndex(
  { tenantId: 1, contractNo: 1 },
  { unique: true }
);
~~~

**Cách B — document tổng hợp làm _id:**

~~~javascript
{
  _id: { tenantId: "t001", contractNo: "CT-2026-001" },
  status: "active"
}
~~~

Cách B có thể hợp lý khi cả hai phần của ID chắc chắn bất biến. Tuy nhiên, document nhúng có đặc tính so sánh phụ thuộc thứ tự field trong những trường hợp so khớp nguyên document, nên phải chuẩn hóa cách tạo khóa. Cách này cũng khó truyền qua URL và khó thay cấu trúc hơn. Nếu chỉ cần ràng buộc không trùng theo hai trường, cách A thường đơn giản và linh hoạt hơn.

## 6. Thực hành: lưu ObjectId và String trong hai collection

Ta tạo một document tài khoản với _id kiểu **ObjectId** và một đơn hàng với _id kiểu **String**. Đơn hàng tham chiếu tài khoản bằng một ObjectId đúng kiểu. Mỗi collection giữ một quy ước kiểu _id, không trộn tùy tiện các kiểu trong cùng collection thật.

Khối lệnh sau chạy trong mongosh. Nó chỉ dọn document có nhãn **labTag = identity-choice-v1** trong hai collection thực hành thuộc database **mongo_identity_lab**. Mỗi lần chạy tạo cùng dữ liệu logic.

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  const tag = "identity-choice-v1";
  const users = labDb.getCollection("lab_identity_users");
  const orders = labDb.getCollection("lab_identity_orders");

  // Chỉ xóa document thuộc dữ liệu thực hành.
  orders.deleteMany({ labTag: tag });
  users.deleteMany({ labTag: tag });

  // _id kiểu ObjectId: giá trị cố định để dễ đối chiếu.
  const userId = new ObjectId("66f000000000000000000001");
  users.insertOne({
    _id: userId,
    labTag: tag,
    tenantId: "t001",
    email: "lan@example.test",
    displayName: "Nguyễn Lan",
    createdAt: ISODate("2026-01-10T08:00:00.000Z")
  });

  // _id kiểu String; trường tham chiếu customerId vẫn là ObjectId.
  orders.insertOne({
    _id: "order-t001-0001",
    labTag: tag,
    tenantId: "t001",
    customerId: userId,
    status: "pending",
    createdAt: ISODate("2026-02-03T09:30:00.000Z")
  });

  users.createIndex(
    { tenantId: 1, email: 1 },
    { unique: true, name: "ux_lab_identity_tenant_email" }
  );

  print("User ObjectId:");
  printjson(users.findOne({ _id: userId }));

  print("Order String ID:");
  printjson(orders.findOne({ _id: "order-t001-0001" }));

  print("Match user using String: " +
    users.countDocuments({ _id: userId.toHexString() }));
  print("Match user using ObjectId: " +
    users.countDocuments({ _id: new ObjectId(userId.toHexString()) }));
})();
~~~

Kết quả của hai phép đếm cuối:

~~~text
Match user using String: 0
Match user using ObjectId: 1
~~~

Đây là minh chứng rằng MongoDB không tự đổi String sang ObjectId trong câu truy vấn. Tương tự, order có **customerId** kiểu ObjectId vì nó cần tham chiếu _id ObjectId của user.

### 6.1. Kiểm tra kiểu _id bằng $type

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  const collections = ["lab_identity_users", "lab_identity_orders"];

  for (const name of collections) {
    print(name);
    printjson(labDb.getCollection(name).aggregate([
      { $match: { labTag: "identity-choice-v1" } },
      { $project: { _id: 1, idType: { $type: "$_id" } } }
    ]).toArray());
  }
})();
~~~

Kết quả mong đợi: **idType = "objectId"** ở lab_identity_users và **idType = "string"** ở lab_identity_orders. Kiểm tra kiểu BSON thực tế đặc biệt quan trọng khi dữ liệu đi qua nhiều ngôn ngữ hoặc bộ ánh xạ Object–Document.

### 6.2. Liên kết bằng $lookup khi kiểu khóa khớp

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  printjson(labDb.getCollection("lab_identity_orders").aggregate([
    { $match: { labTag: "identity-choice-v1" } },
    {
      $lookup: {
        from: "lab_identity_users",
        localField: "customerId",
        foreignField: "_id",
        as: "customer"
      }
    },
    { $project: { _id: 1, customerId: 1, customer: 1 } }
  ]).toArray());
})();
~~~

Mảng **customer** sẽ chứa một document của Nguyễn Lan. Nếu thay customerId trong order thành chuỗi hex, phép $lookup trực tiếp theo ObjectId sẽ không khớp. MongoDB không tự tạo ràng buộc khóa ngoại như hệ quản trị quan hệ: ứng dụng phải giữ tham chiếu nhất quán khi ghi hoặc xóa dữ liệu.

### 6.3. Chạy lại và dọn dữ liệu mẫu

Chạy lại toàn bộ khối seed ở mục 6 để khôi phục dữ liệu về trạng thái khởi đầu. Khi kết thúc bài thực hành, chỉ xóa những document mang nhãn của bài:

~~~javascript
(() => {
  const labDb = db.getSiblingDB("mongo_identity_lab");
  const filter = { labTag: "identity-choice-v1" };
  printjson(labDb.getCollection("lab_identity_orders").deleteMany(filter));
  printjson(labDb.getCollection("lab_identity_users").deleteMany(filter));
})();
~~~

Không dùng dropDatabase hoặc drop collection chỉ để dọn dữ liệu mẫu: chúng có phạm vi rộng hơn. Đoạn dọn rồi chèn lại ở mục 6 không phải một transaction nguyên tử; vì vậy chỉ sử dụng trong môi trường thực hành riêng, không áp dụng nguyên xi cho production đang có ghi đồng thời.

## 7. ObjectId trong ứng dụng Java

Một API thường nhận ID từ URL dưới dạng String:

~~~text
GET /users/66f000000000000000000001
~~~

Nếu database lưu _id kiểu ObjectId, tầng truy xuất Java phải chuyển chuỗi thành **org.bson.types.ObjectId** rồi tạo filter đúng kiểu. Ví dụ với **MongoDB Java Sync Driver**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

public class FindUserByObjectId {
    public static void main(String[] args) {
        String idFromRequest = "66f000000000000000000001";

        if (!ObjectId.isValid(idFromRequest)) {
            throw new IllegalArgumentException("ID không phải 24 ký tự hex hợp lệ");
        }
        ObjectId mongoId = new ObjectId(idFromRequest);

        try (MongoClient client = MongoClients.create(
                "mongodb://127.0.0.1:27017")) {
            MongoDatabase database = client.getDatabase("mongo_identity_lab");
            MongoCollection<Document> users =
                    database.getCollection("lab_identity_users");

            Document user = users.find(
                    Filters.eq("_id", mongoId)
            ).first();

            if (user == null) {
                System.out.println("Không tìm thấy user");
            } else {
                System.out.println(user.toJson());
            }
        }
    }
}
~~~

**ObjectId.isValid** chỉ kiểm tra chuỗi đầu vào có thể diễn giải theo định dạng ObjectId, không chứng minh rằng document tồn tại hoặc người dùng có quyền đọc document. Một cách xử lý API là phân biệt ID sai định dạng (HTTP 400), ID hợp lệ nhưng không tìm thấy (HTTP 404), và quyền truy cập (chính sách bảo mật của ứng dụng).

Trong ứng dụng đa tenant, filter phải có tenant đáng tin cậy từ ngữ cảnh xác thực:

~~~java
Document user = users.find(
    Filters.and(
        Filters.eq("_id", mongoId),
        Filters.eq("tenantId", authenticatedTenantId)
    )
).first();
~~~

Ở đoạn minh họa, **authenticatedTenantId** là biến ứng dụng đã xác thực và cấp giá trị. Không dùng dữ liệu tenant do client tự khai báo làm nguồn phân quyền duy nhất.

### 7.1. Chú ý ánh xạ ID khi dùng Spring Data MongoDB

Một lớp Java khai báo ID bằng String không tự chứng minh MongoDB lưu _id bằng BSON String. Spring Data MongoDB có quy tắc chuyển đổi theo kiểu thuộc tính và annotation như **@Id** hoặc **@MongoId**; tùy mapping, chuỗi trông giống ObjectId có thể được chuyển thành BSON ObjectId.

Khi muốn dùng BSON ObjectId, một lựa chọn rõ ràng là:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("lab_identity_users")
public class LabUser {
    @Id
    private ObjectId id;

    private String tenantId;
    private String email;

    // Constructors, getters và setters...
}
~~~

Nếu yêu cầu lưu chuỗi nguyên vẹn, cần cấu hình ánh xạ String một cách tường minh thay vì dựa vào suy đoán. Khi tích hợp collection có dữ liệu cũ, luôn kiểm tra kiểu thực tế bằng **$type** và xác nhận driver, repository, DTO và API đang thống nhất cách biểu diễn ID.

## 8. ObjectId, index, thời gian và sharding

### 8.1. Index mặc định

Collection thông thường có index tên **_id_**, key **{ _id: 1 }**. Kiểm tra:

~~~javascript
db.getSiblingDB("mongo_identity_lab")
  .getCollection("lab_identity_users")
  .getIndexes();
~~~

Khi ứng dụng truy vấn bằng tenantId, email, customerId hay createdAt, index _id không tự tối ưu mọi bộ lọc. Chọn index bổ sung theo mẫu query thực tế, chẳng hạn **{ tenantId: 1, email: 1 }** hoặc **{ tenantId: 1, createdAt: -1 }**.

### 8.2. Sắp xếp theo thời gian

ObjectId thường có xu hướng tăng theo thời gian **sinh ID**, nhưng sắp xếp theo _id không thay thế yêu cầu nghiệp vụ “mới nhất theo thời điểm tạo đơn” hoặc “mới nhất theo thời điểm cập nhật”. Trên nhiều máy có đồng hồ khác nhau, hoặc khi import dữ liệu cũ, thứ tự ObjectId có thể không phản ánh thời gian lưu.

Nếu màn hình cần đơn hàng mới nhất, lưu createdAt và sort theo trường này; dùng _id làm tie-breaker khi cần thứ tự ổn định:

~~~javascript
db.getSiblingDB("mongo_identity_lab")
  .getCollection("lab_identity_orders")
  .find({ labTag: "identity-choice-v1" })
  .sort({ createdAt: -1, _id: -1 })
  .toArray();
~~~

Khi có nhiều dữ liệu, kiểm tra kế hoạch truy vấn và chọn index khớp điều kiện lọc cùng thứ tự sort.

### 8.3. Shard key và định danh

Trong cluster sharded, shard key quyết định phân bố document. Nếu range shard trên một giá trị tăng gần đơn điệu như ObjectId, ghi mới có thể tập trung ở một vùng dữ liệu; cần cân nhắc chiến lược phân bố và tải ghi. Đồng thời, nếu _id không phải shard key, tính duy nhất của _id có thể chỉ được MongoDB thực thi trong từng shard. Vì thế, khi thiết kế sharding, cần thống nhất cả **cách sinh ID**, **shard key**, **unique index** và **kiểu truy vấn**, thay vì chỉ dựa vào unique index _id của collection thông thường.

## 9. Lỗi thường gặp và cách nhận diện

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| findOne trả null dù chuỗi ID nhìn đúng | Truy vấn bằng String trong khi _id là ObjectId | Kiểm tra $type và chuyển ID sang đúng BSON type |
| BSONError hoặc lỗi tạo ObjectId | Đầu vào không đúng định dạng ObjectId | Kiểm tra hình thức trước khi khởi tạo ObjectId |
| E11000 duplicate key | Trùng _id hoặc vi phạm unique index khác | Đọc tên index trong lỗi; xử lý quy tắc sinh ID/uniqueness |
| Lỗi immutable _id | Cố sửa _id khi document đã tồn tại | Không update _id; thiết kế migration nếu buộc đổi khóa |
| $lookup không tìm thấy document liên quan | Trường tham chiếu khác kiểu BSON với _id đích | Thống nhất kiểu lưu và chuyển đổi tại nơi ghi |
| Sort theo _id khác thứ tự đơn hàng thực tế | Timestamp ID không trùng thời điểm nghiệp vụ | Lưu và sort theo createdAt hoặc trường thời gian phù hợp |
| UUID lưu dạng binary nhưng nhận chuỗi khi query | Mismatch giữa String và BSON UUID hoặc khác representation | Chuẩn hóa hợp đồng UUID và cách chuyển đổi của driver |
| Người dùng đoán được ID và đọc tài nguyên người khác | Ứng dụng thiếu kiểm tra quyền truy cập | Kèm bộ lọc theo owner/tenant từ ngữ cảnh xác thực |
| Đổi email dẫn tới khó cập nhật khóa | Dùng business key dễ thay đổi làm _id | Dùng _id bất biến, unique index riêng cho business key |

## 10. Bài tập tự thực hành

1. **Quan sát cấu trúc:** Sinh ba ObjectId liên tiếp, in toHexString() và getTimestamp(). Giải thích vì sao nhiều ID có thể cùng timestamp nhưng khác nhau và vì sao timestamp này không có độ chính xác mili giây.
2. **Phân biệt kiểu BSON:** Trên dữ liệu mục 6, tìm user bằng chuỗi hex và ObjectId có cùng nội dung. Dùng $type để giải thích vì sao chỉ một truy vấn trả về document.
3. **Liên kết đúng kiểu:** Thay customerId trong order bằng chuỗi hex, chạy lại $lookup, sau đó khôi phục bằng ObjectId. Ghi lại kết quả của mảng customer ở hai lần.
4. **Thiết kế khóa sản phẩm:** Một cửa hàng cần mã SKU có thể đổi và SKU chỉ duy nhất trong từng tenant. Đề xuất kiểu _id, các trường dữ liệu và unique index phù hợp; giải thích vì sao không chọn SKU làm _id.
5. **Định danh đa dịch vụ:** So sánh ObjectId với UUID BSON Binary khi cùng một ID được dùng trong MongoDB, thông điệp sự kiện và API Java. Nêu rõ quy tắc chuyển đổi và representation mà nhóm cần thống nhất.
6. **An toàn truy cập:** Viết câu truy vấn MongoDB dùng cả _id và tenantId đã xác thực. Giải thích vì sao một ID đúng định dạng vẫn chưa có nghĩa người dùng có quyền xem document.
7. **Thời gian và sắp xếp:** Đề xuất cách lưu createdAt và index phục vụ danh sách đơn theo tenant, sort mới nhất trước. Nêu trường hợp sort bằng _id sẽ cho kết quả khác mong đợi.

Trong những bài MongoDB về CRUD, aggregation, index, tham chiếu và thiết kế hệ thống, quy ước định danh cần được giữ thống nhất từ model dữ liệu, lớp Java, API cho đến các document liên quan. **_id là khóa bất biến của document; ObjectId là một lựa chọn mặc định tiện lợi; unique index trên khóa nghiệp vụ và kiểm tra quyền truy cập là những trách nhiệm riêng cần thiết kế rõ ràng.**
