# Tự sinh `_id` và sử dụng định danh do ứng dụng cung cấp trong MongoDB

## 1. Mỗi document cần một định danh

Khi thêm dữ liệu vào collection, MongoDB cần phân biệt một document với mọi document khác trong cùng collection. Trường đặc biệt **`_id`** đóng vai trò đó: nó xác định danh tính của document và là khóa để tìm, cập nhật hoặc xóa chính xác một bản ghi.

Ví dụ collection `orders` có hai đơn hàng:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a001"),
  orderNumber: "VN-2026-0042",
  customerId: "C01",
  status: "NEW"
}

{
  _id: ObjectId("6718d4e0b7e24f52b064a002"),
  orderNumber: "VN-2026-0043",
  customerId: "C02",
  status: "PAID"
}
```

Ở đây có **hai loại định danh**:

- `_id`: định danh của document do MongoDB và driver sử dụng.
- `orderNumber`: mã đơn hàng theo quy tắc nghiệp vụ, dùng trong giao diện, email hoặc hóa đơn.

Hai trường có thể khác nhau, và đó thường là lựa chọn có chủ đích. Ứng dụng cũng có thể dùng trực tiếp mã đơn hàng làm `_id`, nhưng trước hết cần xác định những yêu cầu về tính duy nhất, khả năng thay đổi, kiểu dữ liệu và quy trình tạo mã.

### Những quy tắc cơ bản của `_id`

1. Mọi document được lưu trong một collection thông thường đều có `_id`.
2. Trong một collection thông thường, MongoDB tạo **unique index** trên `_id` và không cho phép hai document cùng giá trị khóa theo quy tắc so sánh của index đó.
3. Sau khi đã chèn, giá trị `_id` của document **không được cập nhật** bằng `$set` hay thao tác thay thế. Khi cần đổi danh tính, ứng dụng thường phải tạo document mới và xử lý chuyển dữ liệu/tham chiếu ở cấp nghiệp vụ.
4. Không bắt buộc `_id` có kiểu `ObjectId`; một số kiểu BSON khác, chẳng hạn String, số hoặc UUID được lưu dưới dạng Binary, cũng có thể dùng khi hợp lệ.
5. Tính duy nhất của `_id` **không có nghĩa một giá trị phải duy nhất trên tất cả collection hoặc tất cả database**.

Với collection được phân mảnh (sharded collection), có thêm điều kiện quan trọng về vị trí áp dụng ràng buộc duy nhất giữa các shard; phần 11 sẽ giải thích.

## 2. Tự sinh `_id`: trường hợp mặc định

Khi chèn document mà không cung cấp trường `_id`, MongoDB và các driver thông dụng tự bảo đảm document được bổ sung định danh. Theo cách dùng thông thường, giá trị được tạo là **BSON ObjectId**.

```javascript
// Ví dụ chạy trong mongosh.
db.customers.insertOne({
  name: "Nguyễn An",
  email: "an@example.test"
});
```

Ví dụ phản hồi:

```javascript
{
  acknowledged: true,
  insertedId: ObjectId("6718d4e0b7e24f52b064a010")
}
```

Giá trị ObjectId phía trên chỉ là **ví dụ minh họa**. Mỗi lần chạy trên dữ liệu khác có thể tạo mã khác. Nếu đọc document vừa lưu:

```javascript
db.customers.findOne({
  _id: ObjectId("6718d4e0b7e24f52b064a010")
});
```

ta thấy `_id` là một trường trong document, mặc dù câu lệnh `insertOne()` ban đầu không chỉ định nó.

### 2.1. Ai thực sự tạo ObjectId?

Nhiều MongoDB driver **tạo `_id` ở phía ứng dụng trước khi gửi lệnh `insert`**. Nhờ vậy, ứng dụng có thể biết định danh sớm và máy chủ nhận document đã có `_id`. Trong trường hợp document gửi đến máy chủ thiếu `_id`, phía máy chủ cũng có cơ chế gán `ObjectId` khi chèn.

Vì vậy, cách nói “MongoDB tự sinh `_id`” chỉ là cách diễn đạt hành vi tổng thể. Không nên mặc định mọi lần sinh ID đều xảy ra **sau khi** máy chủ ghi dữ liệu. Vị trí tạo ID còn tùy API, driver, kiểu codec và cách gửi command.

### 2.2. Tự sinh không có nghĩa có thể dùng mã ID làm bảo mật

ObjectId giúp nhận diện document nhưng **không phải mật khẩu, token đăng nhập hoặc cơ chế phân quyền**. Ai biết một `_id` không tự động được phép đọc document. Ứng dụng phải thực hiện kiểm tra quyền và phạm vi dữ liệu theo người dùng/tenant khi truy vấn.

Tương tự, `_id` không thay thế `createdAt`, không biểu diễn thứ tự nghiệp vụ tuyệt đối, và không tự chứng minh rằng một thao tác ghi đã được xác nhận bền vững.

## 3. ObjectId gồm những gì?

ObjectId là một giá trị BSON dài **12 byte**. Khi hiển thị trong mongosh, nó thường được biểu diễn thành **24 ký tự thập lục phân**:

```text
ObjectId("6718d4e0b7e24f52b064a010")
          |------ 24 ký tự hex ------|
          |---| |--------| |----|
           4B       5B       3B
         thời gian  ngẫu nhiên  bộ đếm
```

Theo cách sinh ObjectId thông dụng:

| Thành phần | Độ dài | Vai trò |
|---|---:|---|
| Timestamp | 4 byte | Số giây tính từ Unix epoch |
| Giá trị ngẫu nhiên theo tiến trình | 5 byte | Giảm khả năng trùng giữa các tiến trình/máy |
| Bộ đếm tăng dần | 3 byte | Phân biệt các ObjectId được tạo liên tiếp trong cùng tiến trình |

MongoDB dùng cách tổ chức này để tạo định danh có **xác suất trùng rất thấp** mà không cần gửi yêu cầu tới một bộ cấp số trung tâm cho từng document. Đây không phải bằng chứng toán học rằng không thể trùng, nên unique index vẫn cần để phát hiện xung đột thực tế.

### 3.1. Lấy thời gian từ ObjectId

Trong mongosh:

```javascript
const id = ObjectId();

print(id.toString());           // Dạng ObjectId("...") tùy ngữ cảnh shell.
print(id.toHexString());        // 24 ký tự hex.
print(id.getTimestamp());       // Ngày/giờ UTC, độ phân giải 1 giây.
```

`getTimestamp()` trả về thời điểm được mã hóa trong ID với **độ phân giải giây**. Thời gian này thường là lúc tiến trình tạo ID, **không bắt buộc** là lúc dữ liệu được chèn thành công hoặc commit trên máy chủ. Có thể xảy ra:

- Ứng dụng tạo ID rồi chờ trước khi gửi dữ liệu.
- Các máy tạo ID có đồng hồ lệch.
- Dữ liệu được import từ hệ thống cũ với ObjectId đã có từ trước.
- Một tiến trình tạo nhiều ID trong cùng một giây.

Nếu nghiệp vụ cần thời điểm tạo đơn chính xác, hãy lưu trường riêng như `createdAt` kiểu BSON Date, có quy tắc xác định nguồn thời gian và múi giờ.

### 3.2. ObjectId có thứ tự tăng không?

Các ObjectId được tạo gần nhau trong **một tiến trình** thường có xu hướng tăng theo thời gian, nhưng không bảo đảm thứ tự toàn cục giữa nhiều máy, nhiều tiến trình hoặc mọi lần chèn. Vì vậy, câu lệnh:

```javascript
db.orders.find().sort({ _id: -1 }).limit(10);
```

có thể hữu ích cho một số tình huống quan sát dữ liệu, nhưng không nên là định nghĩa chính thức của “10 đơn hàng được tạo gần đây nhất”. Với yêu cầu nghiệp vụ rõ ràng, hãy sử dụng `createdAt` và một khóa phụ ổn định để phá trường hợp đồng thời:

```javascript
db.orders.find()
  .sort({ createdAt: -1, _id: -1 })
  .limit(10);
```

Khi dữ liệu lớn, cần thiết kế index tương ứng với điều kiện lọc và sort; việc bổ sung `createdAt` không tự bảo đảm query nhanh.

## 4. Ứng dụng tự cung cấp `_id`

MongoDB cho phép document có `_id` do ứng dụng lựa chọn. Khi trường đã được cung cấp, driver/máy chủ **không được hiểu là yêu cầu sinh một ID khác để thay thế**. Nếu ID trùng với document đã có, thao tác chèn sẽ bị từ chối theo unique index.

### 4.1. Dùng chuỗi làm ID

```javascript
db.orders.insertOne({
  _id: "ORDER-VN-2026-0042",
  customerId: "C01",
  status: "NEW"
});

db.orders.findOne({ _id: "ORDER-VN-2026-0042" });
```

Ưu điểm:

- Dễ đọc, dễ tìm trong log hoặc khi trao đổi với hệ thống khác.
- Có thể dùng mã được sinh ổn định từ sự kiện hoặc nghiệp vụ.
- Tránh phải quản lý một bảng ánh xạ giữa mã nghiệp vụ và `_id` khi hai thứ thật sự giống nhau.

Nhược điểm:

- Nếu giá trị dài, index và khóa lưu trữ thường lớn hơn so với ObjectId 12 byte.
- Nếu có cấu trúc như mã chi nhánh, mã năm, số thứ tự, phải xử lý cấp mã, va chạm, cạnh tranh tạo số và thay đổi quy tắc.
- Nếu ID có thể bị đổi tên theo nghiệp vụ, việc dùng nó làm khóa bất biến sẽ gây phức tạp.

### 4.2. Dùng số nguyên

```javascript
db.products.insertOne({
  _id: NumberLong("100045"),
  name: "Bàn phím cơ",
  price: NumberDecimal("1200000")
});

db.products.findOne({ _id: NumberLong("100045") });
```

MongoDB cho phép định danh dạng số khi hợp lệ. Tuy nhiên, MongoDB **không tự cung cấp** cơ chế tương đương cột `AUTO_INCREMENT` trong quan hệ chỉ vì `_id` là số. Nếu muốn `100045`, `100046`, `100047`… liên tiếp, ứng dụng phải thiết kế cách cấp số an toàn khi nhiều luồng ghi đồng thời.

Một collection đếm tập trung với `findOneAndUpdate` + `$inc` có thể cấp số nguyên tử, nhưng làm tăng thêm một lệnh ghi và có thể trở thành điểm nghẽn khi tải lớn. Cần quyết định có thực sự cần số liền nhau hay chỉ cần ID duy nhất.

### 4.3. Dùng UUID

UUID cũng là một lựa chọn khi cần ID được tạo độc lập giữa nhiều hệ thống. MongoDB hỗ trợ UUID lưu dưới dạng BSON Binary subtype 4 khi biểu diễn đúng cấu hình, còn ứng dụng có thể chủ động lưu biểu diễn chuỗi của UUID:

```javascript
// Cách đơn giản: lưu UUID đã tạo ở ứng dụng dưới dạng String.
db.events.insertOne({
  _id: "c844f8c4-6a35-48cb-91b5-70db31f404f7",
  type: "ORDER_CREATED"
});
```

Chuỗi UUID thường dài hơn dạng Binary 16 byte và có tính chất index khác. Nếu dùng BSON Binary UUID trong Java hoặc các driver khác, cần thống nhất **UUID representation** giữa các ứng dụng, đặc biệt khi hệ thống có dữ liệu cũ từ các chế độ biểu diễn UUID khác nhau.

### 4.4. `_id` là một giá trị BSON, không chỉ là văn bản hiển thị

Hai định danh dưới đây **khác nhau về kiểu**:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a010"),
  label: "ObjectId"
}

{
  _id: "6718d4e0b7e24f52b064a010",
  label: "String"
}
```

Một câu `findOne({ _id: "6718..." })` không tương đương `findOne({ _id: ObjectId("6718...") })`. Đừng gửi ID do driver trả về dưới dạng text rồi mặc định so sánh được với BSON ObjectId mà không chuyển kiểu.

Tương tự, `"42"` là String còn `NumberLong("42")` là số. Các kiểu số của BSON có quy tắc so sánh riêng và có thể so sánh tương đương về giá trị trong những trường hợp nhất định; vì vậy nên chọn **một kiểu ID nhất quán** cho toàn collection thay vì cố tình trộn kiểu.

### 4.5. Không phải mọi giá trị BSON đều phù hợp cho `_id`

MongoDB đặt giới hạn đối với kiểu và hình dạng của trường `_id`. Đặc biệt, không dùng **array** làm `_id`. Các giá trị mang cấu trúc phức tạp hoặc không ổn định cũng thường không phù hợp làm khóa vì khó so sánh, ghi log và trao đổi qua API.

Trong thiết kế mới, hãy ưu tiên một giá trị **nhỏ, ổn định, có kiểu rõ ràng và có khả năng sinh duy nhất** thay vì cố nhét nhiều thuộc tính nghiệp vụ vào `_id`.

## 5. Ví dụ `insertOne()`: mặc định và tự cấp ID

### 5.1. Không truyền `_id`

```javascript
const resultA = db.samples.insertOne({
  kind: "generated",
  description: "Để driver/MongoDB cấp ID"
});

printjson(resultA);
```

Document được chèn có `_id` kiểu ObjectId theo hành vi thường gặp. `insertedId` trong kết quả là ID của document vừa gửi, cho phép ứng dụng dùng để liên kết tác vụ tiếp theo.

### 5.2. Truyền chuỗi ID ổn định

```javascript
const resultB = db.samples.insertOne({
  _id: "sample-B",
  kind: "application-assigned"
});

printjson(resultB.insertedId); // "sample-B"
```

Nếu chèn một document khác với `_id: "sample-B"` vào cùng collection, MongoDB sẽ báo lỗi trùng khóa.

### 5.3. Đặt ObjectId trước khi gọi `insertOne()`

Ngay cả khi chọn kiểu ObjectId, ứng dụng vẫn có thể **chủ động tạo ID**:

```javascript
const orderId = ObjectId();

db.orders.insertOne({
  _id: orderId,
  customerId: "C01",
  status: "NEW"
});

print(orderId.toHexString());
```

Điều này hữu ích khi một quy trình cần giữ ID ổn định qua nhiều lần gửi hoặc muốn gắn nó với một lệnh khác. Nhưng **biết trước ID không đồng nghĩa document chắc chắn đã tồn tại**: sau lỗi mạng, vẫn phải kiểm tra kết quả ghi hoặc sử dụng cơ chế retry an toàn.

### 5.4. Chèn nhiều document có cả ID tự sinh và ID do ứng dụng cung cấp

```javascript
db.samples.insertMany([
  { kind: "generated-1" },
  { _id: "external-01", kind: "custom" },
  { kind: "generated-2" }
]);
```

Những document thiếu `_id` được bổ sung định danh. Document có `"external-01"` giữ nguyên ID được cấp. Kết quả của thao tác chèn nhiều có thể trả danh sách ID đã chèn theo index đầu vào của các document.

Nếu trong một batch có ID trùng, hành vi dừng hoặc tiếp tục những document khác phụ thuộc vào tùy chọn như `ordered` và loại lỗi. Không nên giả định cả batch chèn nhiều là **một transaction nguyên tử**.

## 6. Java MongoDB driver: thao tác với ObjectId và ID tự cấp

Ví dụ dưới đây sử dụng **MongoDB Java Sync Driver** và `org.bson.Document`. Mục tiêu là minh họa cách cấp và đọc định danh; cấu hình kết nối, xác thực và quản lý vòng đời `MongoClient` cần phù hợp với ứng dụng thực tế.

### 6.1. Để driver tạo ObjectId

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;
import org.bson.types.ObjectId;

public class GeneratedIdExample {
    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("learn_id");
            MongoCollection<Document> orders = database.getCollection("orders");

            Document order = new Document("customerId", "C01")
                    .append("status", "NEW");

            InsertOneResult result = orders.insertOne(order);
            ObjectId id = result.getInsertedId().asObjectId().getValue();

            System.out.println("Inserted _id: " + id.toHexString());
            Document stored = orders.find(new Document("_id", id)).first();
            System.out.println(stored);
        }
    }
}
```

Điểm cần ghi nhớ:

- `InsertOneResult.getInsertedId()` cung cấp BSON ID của thao tác chèn được xác nhận.
- `asObjectId()` chỉ phù hợp khi ID thực sự có kiểu ObjectId. Với ID String hoặc Binary UUID, phải đọc đúng kiểu.
- Nếu thao tác ghi không được xác nhận hoặc gặp lỗi, không nên tùy tiện gọi `getInsertedId()` và coi là bằng chứng dữ liệu đã commit. Cần xử lý ngoại lệ và yêu cầu write concern.

Nhiều phiên bản driver có thể bổ sung `_id` vào `Document` đầu vào khi mã hóa thao tác chèn, nhưng sử dụng kết quả `InsertOneResult` giúp diễn đạt rõ việc nhận ID của lệnh.

### 6.2. Tự cấp ObjectId trong Java

```java
ObjectId id = new ObjectId();

Document order = new Document("_id", id)
        .append("customerId", "C02")
        .append("status", "NEW");

orders.insertOne(order);

// Dùng đúng BSON ObjectId khi tìm.
Document stored = orders.find(new Document("_id", id)).first();
```

Ở đây `new ObjectId()` tạo giá trị trong ứng dụng, còn MongoDB chịu trách nhiệm kiểm tra tính duy nhất qua index khi ghi.

### 6.3. Tự cấp chuỗi nghiệp vụ trong Java

```java
String orderId = "ORDER-VN-2026-0042";

Document order = new Document("_id", orderId)
        .append("customerId", "C03")
        .append("status", "PAID");

orders.insertOne(order);

// Không chuyển chuỗi này sang ObjectId.
Document stored = orders.find(new Document("_id", orderId)).first();
```

Nếu cùng một mã được sử dụng lại, server phát hiện trùng ID. Chương trình phải quyết định đó là **lỗi nghiệp vụ**, **lần gửi lại của cùng một yêu cầu**, hay **bằng chứng có hai yêu cầu đang tranh chấp một mã**.

### 6.4. Dùng UUID được tạo trong ứng dụng

```java
import java.util.UUID;

String eventId = UUID.randomUUID().toString();

Document event = new Document("_id", eventId)
        .append("type", "ORDER_CREATED");

events.insertOne(event);
```

Ở ví dụ này UUID được lưu như **BSON String** vì mã Java đã gọi `toString()`. Nếu muốn lưu UUID theo BSON Binary subtype 4, cần dùng kiểu BSON/codec phù hợp và thống nhất representation. Hai cách lưu **không tương đương** trong truy vấn.

## 7. Quy tắc duy nhất, lỗi trùng và tính bất biến của `_id`

### 7.1. Duplicate key là kết quả bình thường khi ID trùng

```javascript
db.orders.insertOne({
  _id: "ORDER-0001",
  status: "NEW"
});

db.orders.insertOne({
  _id: "ORDER-0001",
  status: "PAID"
});
```

Lệnh thứ hai sẽ không tạo một đơn hàng mới có cùng `_id`. Máy chủ báo lỗi duplicate key, thường nhận diện bằng mã **11000** và thông báo có `E11000 duplicate key error`. Lệnh chèn bị lỗi **không tự cập nhật** document có trước.

Điều quan trọng là không xử lý mọi lỗi trùng theo cùng một cách:

- Hai yêu cầu thực sự khác nhau chọn cùng mã: cần phát hiện va chạm và quyết định mã mới hoặc báo lỗi nghiệp vụ.
- Một yêu cầu gửi lại sau timeout: có thể document đã tồn tại do lần gửi trước thành công; cần kiểm tra xem nó có phải **cùng giao dịch logic**.
- Cùng một mã được sử dụng cho nội dung khác: không được coi là thành công chỉ vì khóa đã tồn tại.

### 7.2. Không thể sửa `_id` bằng `$set`

```javascript
// Không hợp lệ: MongoDB không cho đổi _id của một document.
db.orders.updateOne(
  { _id: "ORDER-0001" },
  { $set: { _id: "ORDER-0002" } }
);
```

Lệnh thay thế document cũng không được thay giá trị `_id` của document đang có. Nếu mã đơn nghiệp vụ có thể đổi sau khi phát hành, thường tốt hơn để mã đó ở trường `orderNumber` và giữ `_id` là một định danh nội bộ ổn định.

### 7.3. Ràng buộc `_id` và ràng buộc nghiệp vụ là hai việc khác nhau

Ví dụ muốn `orderNumber` duy nhất trong phạm vi một doanh nghiệp:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true }
);
```

Khi dùng `_id` dạng ObjectId, unique compound index trên `tenantId, orderNumber` kiểm tra một **quy tắc nghiệp vụ riêng**. Một khách hàng có thể tạo hai yêu cầu với hai ObjectId khác nhau nhưng cùng mã đơn; `_id` không thể tự ngăn va chạm `orderNumber`.

Với sharded collection, unique index còn có ràng buộc theo shard key. Trước khi triển khai unique compound index trong cụm phân mảnh, cần kiểm tra liệu cấu hình shard key cho phép bảo đảm duy nhất toàn cụm hay không.

## 8. Cấp ID và bài toán gửi lại yêu cầu

Trong hệ thống thực tế, ứng dụng có thể gửi `insertOne()`, máy chủ đã ghi thành công, nhưng kết nối bị đứt trước khi phản hồi trở về. Ứng dụng không luôn biết lần chèn đã xảy ra hay chưa. Đây là lý do **lựa chọn ID ảnh hưởng cách retry**.

### 8.1. Tạo ID mới mỗi lần retry có thể tạo bản ghi trùng nghiệp vụ

Giả sử một request HTTP tạo đơn hàng bị timeout:

```text
POST /orders (request X)
        |
        v
Ứng dụng tạo ObjectId A
        |
        v
MongoDB ghi đơn A thành công
        |
       mất phản hồi
        |
        v
Ứng dụng thử lại request X
        |
        v
Ứng dụng tạo ObjectId B
        |
        v
MongoDB ghi đơn B thành công
```

Từ góc nhìn database, A và B khác `_id`, nên unique index không ngăn được hai document. Nhưng về nghiệp vụ, đó có thể là **cùng một đơn**.

Đừng nhầm chuyện này với **retryable writes** của driver. Khi một driver hỗ trợ retryable write, nó sử dụng thông tin phiên và số thứ tự thao tác để xử lý một số lỗi tạm thời theo giao thức. Điều đó khác với một ứng dụng tự xây lại request, tạo `_id` mới rồi gửi thao tác mới.

### 8.2. Giữ ID ổn định cho cùng một yêu cầu logic

Một giải pháp là xác định mã định danh ở cấp request và dùng lại trong mọi lần thử:

```javascript
// requestId đã được tạo từ trước và giữ nguyên trong các lần retry.
const requestId = "REQ-2026-10-001";

db.orders.insertOne({
  _id: requestId,
  customerId: "C01",
  status: "NEW"
});
```

Nếu đã tồn tại một đơn với `_id` đó, lệnh chèn lại bị lỗi trùng khóa. Khi gặp lỗi, ứng dụng có thể tìm document theo cùng `_id`, so sánh dữ liệu hoặc mã kiểm chứng của request, sau đó quyết định trả lại kết quả cũ. **Không được coi duplicate key là thành công nếu nội dung hoặc quyền sở hữu không khớp.**

### 8.3. Dùng ObjectId nội bộ và khóa idempotency riêng

Không nhất thiết dùng khóa request làm `_id`. Ví dụ một API đa tenant có thể giữ ObjectId làm ID nội bộ, đồng thời đặt ràng buộc nghiệp vụ:

```javascript
db.orders.createIndex(
  { tenantId: 1, requestKey: 1 },
  { unique: true }
);

db.orders.insertOne({
  tenantId: "T01",
  requestKey: "REQ-2026-10-001",
  customerId: "C01",
  status: "NEW"
});
```

Khi retry, ứng dụng dùng **cùng `tenantId` và `requestKey`**. Unique index ngăn thêm một document khác cho cùng khóa yêu cầu trong phạm vi tenant. Cần bảo đảm khóa request chỉ được dùng cho cùng nội dung nghiệp vụ, có quy tắc lưu giữ phù hợp và không bị sử dụng chéo giữa các tài khoản.

### 8.4. Upsert với `$setOnInsert`

Nếu nghiệp vụ muốn “nếu chưa tồn tại thì thêm, nếu đã có thì giữ nguyên”, có thể dùng `updateOne()` với `upsert: true`:

```javascript
db.orders.updateOne(
  { _id: "REQ-2026-10-001" },
  {
    $setOnInsert: {
      customerId: "C01",
      status: "NEW",
      createdAt: ISODate("2026-10-20T09:00:00Z")
    }
  },
  { upsert: true }
);
```

Với `_id` đã tồn tại, thao tác không tạo document mới; với `_id` chưa có, nó thêm document. Unique index giúp ngăn hai document có cùng `_id` khi nhiều yêu cầu đến đồng thời. Trong trường hợp tranh chấp đồng thời, một thao tác vẫn có thể nhận duplicate key hoặc lỗi tạm thời tùy điều kiện, nên ứng dụng cần xử lý retry và readback phù hợp.

Không dùng `$set` để ghi đè toàn bộ trường nghiệp vụ trong mọi lần thử nếu mục tiêu là “tạo đúng một lần”; `$setOnInsert` phân biệt rõ **dữ liệu chỉ dùng khi tạo**.

Nếu yêu cầu có bước ngoài MongoDB như trừ tiền hoặc gửi email, idempotent insert **không tự bảo đảm toàn bộ chuỗi thao tác bên ngoài chỉ chạy một lần**. Cần cơ chế nghiệp vụ và ghi nhận trạng thái riêng cho các tác động đó.

## 9. Nên dùng khóa tự sinh hay khóa nghiệp vụ làm `_id`?

### 9.1. Khóa thay thế (surrogate key)

Một khóa không mang nội dung nghiệp vụ, chẳng hạn ObjectId hoặc UUID ngẫu nhiên:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a020"),
  employeeCode: "EMP-001",
  email: "an@example.test",
  fullName: "Nguyễn An"
}
```

Ưu điểm là ID ổn định ngay cả khi email hoặc mã nhân viên phải thay đổi. Nó phù hợp với document tồn tại lâu, được nhiều collection tham chiếu và có thuộc tính nghiệp vụ có thể cập nhật.

Nhược điểm là đôi khi ứng dụng cần thêm index duy nhất cho mã nghiệp vụ, và phải truyền/tra cứu cả `_id` lẫn mã đó.

### 9.2. Khóa tự nhiên (natural key)

Một trường đã có ý nghĩa nghiệp vụ và được quy định là duy nhất, chẳng hạn một mã danh mục không bao giờ thay đổi:

```javascript
{
  _id: "COUNTRY-VN",
  displayName: "Việt Nam"
}
```

Ưu điểm là đơn giản trong các hệ thống mà mã đó đã ổn định, kích thước nhỏ và có thể thống nhất trên mọi ứng dụng.

Nhược điểm là nếu quy tắc mã đổi hoặc dữ liệu có nhiều cách viết (chữ hoa/thường, khoảng trắng, Unicode), phải xử lý chuẩn hóa. Đặc biệt, **email, số điện thoại, tên hiển thị** thường có thể thay đổi và còn liên quan thông tin cá nhân; ít phù hợp làm `_id` bất biến.

### 9.3. Bảng quyết định

| Tình huống | Có thể chọn | Lý do |
|---|---|---|
| Document mới, không có khóa nghiệp vụ ổn định | ObjectId tự sinh | Ít cấu hình, ID ngắn, driver hỗ trợ phổ biến |
| Hệ thống phân tán cần ID được tạo trước khi ghi | ObjectId tạo ở ứng dụng hoặc UUID | Không cần một bộ cấp số đồng bộ cho mỗi thao tác |
| Mã nghiệp vụ thật sự bất biến và duy nhất trong collection | Chuỗi mã nghiệp vụ làm `_id` | Truy cập trực tiếp bằng mã, tránh ánh xạ thêm |
| Mã nghiệp vụ có thể đổi | ObjectId/UUID làm `_id`, mã ở trường riêng | Giữ tham chiếu ổn định |
| Người dùng có thể trùng mã ở các tenant | ID toàn cục riêng và unique index theo tenant | Tách danh tính document với phạm vi duy nhất của nghiệp vụ |
| API có retry, cần chống tạo đơn trùng | ID/request key ổn định + unique index | Có điểm nhận diện một thao tác logic |
| Cần hiển thị số hóa đơn tăng liên tiếp | Có thể giữ ObjectId nội bộ và cấp số hóa đơn riêng | Quy tắc đánh số hóa đơn khác yêu cầu ID của document |

Không nên dùng khả năng “trông giống số tăng dần” của ObjectId để giải quyết yêu cầu cấp số kế toán liên tục. Nếu nghiệp vụ bắt buộc các số được cấp có tính chất pháp lý hoặc không được bỏ số, phải thiết kế một quy trình cấp số riêng với quy tắc rollback/hủy và đối soát rõ ràng.

## 10. Ảnh hưởng đến truy vấn, index và dữ liệu tham chiếu

### 10.1. Truy vấn theo `_id` có index mặc định

```javascript
db.orders.findOne({
  _id: ObjectId("6718d4e0b7e24f52b064a020")
});
```

Collection thông thường có unique index trên `_id`, nên phép tìm chính xác theo `_id` thường có thể sử dụng index hiệu quả. Nhưng hiệu năng thực tế còn phụ thuộc tầng mạng, kích thước tài liệu, cache và điều kiện triển khai.

Thử quan sát kế hoạch:

```javascript
db.orders.find({
  _id: ObjectId("6718d4e0b7e24f52b064a020")
}).explain("executionStats");
```

Những trường như `IXSCAN`, `FETCH`, `totalKeysExamined`, `totalDocsExamined` cho biết server đã đọc khóa và tài liệu như thế nào. Với data rất nhỏ hoặc ở những storage/index engine khác nhau, cấu trúc explain có thể khác; đừng suy diễn chỉ từ một tên stage.

### 10.2. Reference phải giữ đúng kiểu `_id`

Giả sử collection `customers` dùng ObjectId làm khóa:

```javascript
{
  _id: ObjectId("6718d4e0b7e24f52b064a099"),
  fullName: "Nguyễn An"
}
```

Khi đơn hàng tham chiếu đến khách hàng, nên lưu cùng kiểu BSON:

```javascript
{
  _id: "ORDER-0001",
  customerId: ObjectId("6718d4e0b7e24f52b064a099")
}
```

Nếu `customerId` lưu chuỗi `"6718d4..."` trong khi `customers._id` là ObjectId, phép so sánh trực tiếp hoặc `$lookup` bằng hai trường có thể không khớp như mong muốn. Chuẩn hóa kiểu ở ranh giới API/driver trước khi lưu reference.

### 10.3. Không thay `_id` khi có nhiều tham chiếu

Nếu document khách hàng có hàng nghìn đơn hàng trỏ tới `customerId`, đổi khóa của khách hàng thành một giá trị khác sẽ buộc ứng dụng di chuyển hoặc cập nhật quan hệ tham chiếu, đồng thời phải giải quyết các thao tác đang chạy. Vì vậy, chọn `_id` **bền vững trong suốt vòng đời document** thường quan trọng hơn việc có thể đọc hiểu mã bằng mắt.

### 10.4. Kích thước và phân bố khóa

Các kiểu ID có ảnh hưởng đến cấu trúc index:

- ObjectId có 12 byte và thường có tính gần tăng theo thời gian tạo.
- UUID v4 mang tính ngẫu nhiên, giúp phân bố giá trị khác nhưng có thể ảnh hưởng độ cục bộ của thao tác insert vào index.
- Chuỗi dài tốn thêm không gian khóa index và dung lượng truyền.
- Mã tăng tuần tự có thể tạo xu hướng ghi tập trung trên các khoảng khóa trong một số topology hoặc kiểu sharding.

Không có kiểu ID “nhanh nhất” cho mọi hệ thống. Chọn trước theo yêu cầu nghiệp vụ, sau đó đo đường ghi/index và phân bố shard khi tải thực tế đủ lớn.

## 11. `_id` khi dùng sharding: lưu ý về tính duy nhất toàn cụm

Trong collection không phân mảnh, unique `_id` index bảo đảm không có hai document cùng khóa trong collection. Với **sharded collection**, cần phân biệt hai tình huống:

- Nếu **`_id` là shard key** hoặc việc phân mảnh đáp ứng điều kiện để ràng buộc unique áp dụng toàn cụm, MongoDB có thể bảo đảm khóa duy nhất theo thiết kế đó.
- Nếu **`_id` không phải shard key** và ràng buộc unique `_id` không trải trên tất cả shard, MongoDB có thể chỉ bảo đảm tính duy nhất của `_id` **trong từng shard**. Ứng dụng phải chịu trách nhiệm tạo `_id` duy nhất trên toàn các shard nếu nghiệp vụ yêu cầu.

Ví dụ, sharded collection phân bố theo `tenantId`; một mã `_id: "ORDER-0001"` do hai tenant tự cấp có thể được lưu trên những shard khác nhau nếu hệ thống không có cơ chế kiểm soát toàn cục tương ứng. Không nên mặc định ràng buộc `_id` làm nhiệm vụ thay cho một định nghĩa định danh **đa tenant**.

Đối với unique index tùy chọn trên những trường khác, MongoDB đặt các quy tắc liên quan **shard key prefix** và cấu hình sharding. Hãy thiết kế shard key, phạm vi tenant và khóa duy nhất cùng nhau trước khi phân mảnh dữ liệu, đặc biệt nếu dự định dùng mã do ứng dụng tạo.

Trong các hệ thống nhiều shard, ID ngẫu nhiên hay có tính tăng theo thời gian còn ảnh hưởng cách dữ liệu được phân bố và định tuyến. Tuy nhiên, chỉ đổi kiểu ID **không tự giải quyết** vấn đề phân bố nếu shard key không dùng trường ID đó.

## 12. Những lỗi thường gặp khi tự cấp ID

| Tình huống | Hậu quả | Cách xử lý |
|---|---|---|
| Chèn hai document cùng `_id` | Lỗi duplicate key | Xác định va chạm hay retry cùng yêu cầu; không bỏ qua bừa |
| Gửi ObjectId dưới dạng chuỗi | `find` hoặc `$lookup` không khớp kiểu | Chuyển đúng BSON ObjectId trước khi truy vấn |
| Dùng email làm `_id` | Không đổi được khóa khi email thay đổi | Giữ ID ổn định, lưu email thành trường riêng có index phù hợp |
| Tự tạo một ObjectId mới cho mỗi lần retry HTTP | Có thể chèn nhiều bản ghi cho một yêu cầu logic | Dùng khóa idempotency ổn định hoặc trạng thái nghiệp vụ có kiểm soát |
| Coi ObjectId như timestamp chính xác | Báo cáo tạo đơn sai thời điểm | Lưu `createdAt` riêng |
| Coi ObjectId khó đoán là quyền truy cập | Nguy cơ lộ dữ liệu khi có ID | Áp dụng xác thực, ủy quyền và điều kiện tenant |
| Coi số `_id` là tự tăng tự động | Va chạm ID khi nhiều tiến trình cấp số | Dùng bộ cấp số được thiết kế nguyên tử hoặc ID phân tán |
| Dùng ID khác kiểu ở dữ liệu tham chiếu | Không kết hợp được dữ liệu | Chuẩn hóa kiểu BSON giữa các collection |
| Coi unique `_id` luôn có hiệu lực toàn sharded collection | Có thể trùng giữa shard khi thiết kế không phù hợp | Xác định shard key và cơ chế duy nhất toàn cụm |
| Đổi `_id` bằng `$set` | Lỗi vì khóa bất biến | Giữ `_id` ổn định; thay đổi mã nghiệp vụ ở trường riêng |

## 13. Thực hành có thể chạy trong mongosh

Dùng collection riêng để quan sát hành vi. Những ví dụ sau có thể tạo dữ liệu và cố ý gây lỗi duplicate key; không chạy trên collection sản xuất.

### Bài tập 1 — So sánh ID tự sinh và ID do ứng dụng cấp

```javascript
db.idPractice.insertMany([
  { label: "auto-1" },
  { label: "auto-2" },
  { _id: "APP-001", label: "custom-string" },
  { _id: NumberLong("999"), label: "custom-number" }
]);

db.idPractice.find().sort({ label: 1 });
```

Quan sát kiểu và giá trị `_id` thực tế của mỗi document. Dùng câu truy vấn:

```javascript
db.idPractice.aggregate([
  {
    $project: {
      label: 1,
      idType: { $type: "$_id" }
    }
  }
]);
```

Kết quả `idType` giúp thấy `objectId`, `string` và `long` là các kiểu BSON khác nhau.

### Bài tập 2 — Tạo lỗi trùng khóa

```javascript
db.idPractice.insertOne({
  _id: "APP-001",
  label: "duplicate"
});
```

Quan sát lỗi duplicate key. Sau đó chạy:

```javascript
db.idPractice.findOne({ _id: "APP-001" });
```

Document ban đầu vẫn tồn tại; `insertOne()` thứ hai không thay thế nó. Hãy giải thích vì sao unique index ở `_id` bảo đảm tính duy nhất nhưng **không tự xác định** hai request có cùng ý nghĩa nghiệp vụ hay không.

### Bài tập 3 — Kiểu ID khi tìm kiếm

```javascript
const id = new ObjectId();

db.idPractice.insertOne({
  _id: id,
  label: "object-id"
});

db.idPractice.findOne({ _id: id });
db.idPractice.findOne({ _id: id.toHexString() });
```

Dòng đầu tìm bằng đúng ObjectId nên có thể trả document; dòng sau tìm bằng String có cùng ký tự hiển thị nên không khớp document đó. Hãy mô tả chính xác vì sao.

### Bài tập 4 — Cùng một yêu cầu gửi hai lần

```javascript
const requestId = "REQ-001";

db.idempotentOrders.updateOne(
  { _id: requestId },
  {
    $setOnInsert: {
      customerId: "C01",
      status: "NEW"
    }
  },
  { upsert: true }
);

// Thử gửi lại chính lệnh trên.
db.idempotentOrders.updateOne(
  { _id: requestId },
  {
    $setOnInsert: {
      customerId: "C01",
      status: "NEW"
    }
  },
  { upsert: true }
);

db.idempotentOrders.find({ _id: requestId });
```

Quan sát `matchedCount`, `modifiedCount` và `upsertedId` nếu có trong kết quả từng lệnh. Tại sao sau hai lần thực thi lại chỉ có một document? Nếu lần gửi thứ hai mang `customerId` khác, ứng dụng cần bổ sung kiểm tra nghiệp vụ nào?

### Bài tập 5 — Chọn chiến lược ID cho ba loại dữ liệu

Thiết kế định danh cho:

1. Collection `products` với mã SKU có thể đổi do nhà cung cấp.
2. Collection `orders` có số hóa đơn phải tuân thủ quy tắc đánh số riêng.
3. Collection `events` ghi sự kiện từ nhiều dịch vụ, có thể nhận lại cùng sự kiện qua hàng đợi.

Với mỗi trường hợp, hãy quyết định kiểu `_id`, trường nghiệp vụ nào cần index duy nhất, nguồn tạo định danh và cách retry. Không nên chọn một kiểu ID chỉ vì nó dễ đọc, khi mục tiêu quan trọng hơn là **ổn định và không tạo dữ liệu trùng**.

## 14. Ghi nhớ khi thiết kế

**`_id` là danh tính của document, còn mã nghiệp vụ có thể là một khái niệm khác.** Để MongoDB/driver tạo ObjectId là lựa chọn mặc định hợp lý khi chưa có định danh nghiệp vụ thực sự ổn định.

**Ứng dụng được quyền cấp `_id` của mình**, miễn giá trị hợp lệ, có kiểu nhất quán và không vi phạm tính duy nhất theo phạm vi MongoDB áp dụng. Chuỗi, số, UUID và ObjectId đều có các đánh đổi riêng về kích thước, phân bố, khả năng thay đổi và cách xử lý lỗi.

**ObjectId không phải thời điểm tạo chính thức, quyền truy cập hay khóa idempotency tự động.** Khi hệ thống phân tán có retry, hãy dùng định danh yêu cầu ổn định hoặc unique business key và xác minh nội dung trùng khớp.

**Chọn một ID bền vững từ đầu.** Dữ liệu tham chiếu, index, sharding và các API phụ thuộc vào kiểu và giá trị của `_id`; đổi chiến lược sau khi đã có nhiều dữ liệu thường khó hơn việc tách định danh nội bộ khỏi những trường nghiệp vụ có thể thay đổi ngay từ đầu.
