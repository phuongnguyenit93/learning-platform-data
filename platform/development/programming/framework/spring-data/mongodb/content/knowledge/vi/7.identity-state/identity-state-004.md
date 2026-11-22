# `@MongoId` để điều khiển kiểu định danh

Trong MongoDB, mỗi document có một trường `_id` dùng để định danh duy nhất **trong phạm vi collection**. Với **Spring Data MongoDB**, thuộc tính Java như `id` thường được ánh xạ tới `_id`. Tuy nhiên, **kiểu khai báo trong Java không nhất thiết trùng với kiểu BSON thực sự được lưu trong MongoDB Server**. Ví dụ một chuỗi 24 ký tự hex có thể được lưu dưới dạng BSON `String` hoặc BSON `ObjectId`; hai giá trị đó nhìn giống nhau khi hiển thị nhưng **không phải cùng một giá trị khi so khớp**.

Annotation `@MongoId` cho phép kiểm soát cách Spring Data MongoDB biểu diễn giá trị định danh khi đọc/ghi. Bài học thuộc chương **Định danh và trạng thái** của module `SPRING_DATA_MONGODB`. Ta sẽ xem sự khác biệt giữa `@MongoId` và `@Id`, lựa chọn định danh theo yêu cầu nghiệp vụ, truy vấn qua repository hoặc `MongoTemplate`, nhận diện dữ liệu sai kiểu, kiểm thử trên MongoDB thật và cân nhắc khi thay đổi kiểu `_id` đã lưu.

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của `_id`, `ObjectId`, `String` và quy tắc ánh xạ ID trong Spring Data MongoDB.
- Phân biệt `@Id`, `@MongoId` mặc định và `@MongoId(FieldType.OBJECT_ID)`.
- Thiết kế entity với **ID chuỗi nguyên dạng** hoặc **ID lưu bằng BSON ObjectId** theo một quy ước rõ ràng.
- Kiểm tra BSON type thực tế bằng `mongosh` và driver, tránh lỗi “cùng chữ nhưng khác kiểu”.
- Biết khi nào cần giữ ổn định ID, xử lý tham chiếu, index, cập nhật, kiểm thử và di trú dữ liệu.

## 1. `_id` là gì và vì sao kiểu BSON quan trọng?

Trong một collection, MongoDB sử dụng `_id` làm khóa định danh của document. Nếu thao tác insert không cung cấp `_id`, driver hoặc MongoDB có thể tạo giá trị `ObjectId`. Dù vậy, MongoDB **không bắt buộc mọi document phải có `_id` kiểu `ObjectId`**: ứng dụng có thể dùng chuỗi, số hoặc nhiều kiểu BSON được hỗ trợ khác, miễn đáp ứng ràng buộc của `_id`.

MongoDB tự duy trì **unique index** cho `_id` trong collection thông thường. Hai document trong cùng collection không được có cùng giá trị `_id`. Kiểu dữ liệu là một phần của phép so sánh nên hai ID sau **khác nhau**:

```javascript
// Document A: _id là BSON String
{
  _id: "507f1f77bcf86cd799439011",
  name: "Khách hàng A"
}

// Document B: _id là BSON ObjectId
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  name: "Khách hàng B"
}
```

Trong `mongosh`, hai truy vấn dưới đây tìm **hai kiểu BSON khác nhau**:

```javascript
db.customers.findOne({ _id: "507f1f77bcf86cd799439011" });
db.customers.findOne({ _id: ObjectId("507f1f77bcf86cd799439011") });
```

Một `ObjectId` thường được hiển thị bằng **24 ký tự hex**, biểu diễn 12 byte dữ liệu. Chuỗi 24 ký tự hex là **cách biểu diễn** có thể chuyển thành ObjectId, nhưng bản thân chuỗi Java không tự động trở thành BSON ObjectId; việc có chuyển đổi hay không phụ thuộc mapping/codec được sử dụng.

> **Điểm mấu chốt:** khi điều tra lỗi tìm kiếm theo ID, cần kiểm tra đồng thời **giá trị** và **kiểu BSON** của `_id`. Chỉ in `id.toString()` hoặc so chuỗi hex có thể che giấu vấn đề.

## 2. `@Id` và `@MongoId` khác nhau ở đâu?

Spring Data MongoDB có một số cách nhận diện thuộc tính ID:

1. `@Id` từ `org.springframework.data.annotation.Id` đánh dấu thuộc tính ID và áp dụng quy tắc chuyển đổi ID mặc định của Spring Data MongoDB.
2. `@MongoId` từ `org.springframework.data.mongodb.core.mapping.MongoId` vẫn xác định thuộc tính làm ID, nhưng cho phép chỉ định **kiểu BSON đích** qua `FieldType`.
3. Một thuộc tính có tên `id` hoặc `_id` có thể được mapping theo convention trong những trường hợp không dùng annotation; khi cần kiểm soát kiểu một cách tường minh, nên khai báo annotation phù hợp.

Ba cách thường gặp:

| Khai báo trong Java | Giá trị là chuỗi hex hợp lệ 24 ký tự | Kiểu BSON `_id` thường được ghi |
| --- | --- | --- |
| `@Id String id` | Spring Data áp dụng chuyển đổi mặc định; chuỗi chuyển được thành `ObjectId` | `ObjectId` |
| `@MongoId String id` | Dùng kiểu ngầm định (`FieldType.IMPLICIT`), không ép chuỗi hex sang `ObjectId` | `String` |
| `@MongoId(FieldType.OBJECT_ID) String id` | Yêu cầu chuyển ID sang dạng ObjectId khi có thể | `ObjectId` |
| `@MongoId ObjectId id` | Bản thân thuộc tính Java đã là `ObjectId` | `ObjectId` |

Các quy tắc trên mô tả **Spring Data MongoDB với bộ chuyển đổi mapping mặc định**. Converter tùy chỉnh hoặc thay đổi framework có thể ảnh hưởng hành vi; với một dự án cụ thể, hãy xác nhận bằng kiểm thử tích hợp và kiểm tra dữ liệu BSON thực lưu. Đừng đoán kiểu `_id` chỉ từ khai báo `String`.

### 2.1. `@Id`: chuyển đổi theo mặc định

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "legacyCustomers")
public record LegacyCustomer(
        @Id String id,
        String name
) {}
```

Nếu lưu một `LegacyCustomer` có `id` bằng chuỗi `"507f1f77bcf86cd799439011"`, Spring Data thường chuyển giá trị này thành BSON `ObjectId` khi ghi. Với chuỗi **không hợp lệ theo định dạng ObjectId**, mapper có thể giữ dưới dạng String.

Điều này dễ tạo ra collection có `_id` **khác kiểu** nếu ứng dụng chấp nhận cả ID tự do và ID trông như ObjectId. Vì vậy, khi chủ đích dùng **mã chuỗi nghiệp vụ**, `@MongoId` mặc định là lựa chọn dễ hiểu hơn.

### 2.2. `@MongoId`: giữ ID chuỗi theo kiểu khai báo

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "customers")
public record Customer(
        @MongoId String id,
        String name,
        int loyaltyLevel
) {}
```

Khi lưu `Customer` với ID `"CUS-1001"` hoặc `"507f1f77bcf86cd799439011"`, kiểu BSON mục tiêu vẫn là **String**. Đây là lựa chọn phù hợp khi ID đến từ một hệ thống bên ngoài, mã nghiệp vụ có quy tắc riêng hoặc yêu cầu mọi ID được ghi nguyên dạng chuỗi.

Về mặt metadata, `@MongoId` mặc định tương ứng với `FieldType.IMPLICIT`: giữ cách biểu diễn theo kiểu dữ liệu Java và converter mặc định, **không áp dụng quy tắc chuyển chuỗi ID 24-hex thành ObjectId như `@Id`**.

### 2.3. `@MongoId(FieldType.OBJECT_ID)`: yêu cầu BSON ObjectId

```java
import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "auditEvents")
public record AuditEvent(
        @MongoId(FieldType.OBJECT_ID) String id,
        String action,
        Instant occurredAt
) {}
```

Khi `id` bằng `"507f1f77bcf86cd799439011"`, Spring Data có thể chuyển nó sang BSON `ObjectId("507f1f77bcf86cd799439011")` trước khi ghi. Phía Java vẫn thao tác trên trường `String`, nhưng giá trị lưu trên server là `ObjectId`.

**Không coi `FieldType.OBJECT_ID` là công cụ xác thực dữ liệu đầu vào.** Với chuỗi không thể chuyển thành ObjectId, quy tắc chuyển đổi mặc định có thể giữ nó ở dạng String thay vì bắt buộc mọi trường hợp phải báo lỗi. Vì thế, nếu mục tiêu là collection chỉ có `_id` kiểu ObjectId, hãy **kiểm tra định dạng đầu vào** hoặc dùng trực tiếp thuộc tính Java `ObjectId`.

## 3. Chọn kiểu ID từ yêu cầu nghiệp vụ

Hãy chọn loại ID **trước khi có dữ liệu thật** và ghi thành quy ước cho từng collection:

| Nhu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Document nội bộ, không có ID nghiệp vụ sẵn | `ObjectId` hoặc chuỗi biểu diễn ObjectId có kiểm soát | Tương thích tự nhiên với hệ sinh thái MongoDB |
| Mã khách hàng hoặc mã đơn do hệ thống ngoài cung cấp | `@MongoId String id` | Giữ nguyên ID chuỗi, bao gồm những chuỗi tình cờ giống ObjectId |
| API ngoài nhận/trả ID dạng hex nhưng server lưu ObjectId | `@MongoId(FieldType.OBJECT_ID) String id` | Phía Java/API dùng String, MongoDB dùng ObjectId nếu ID hợp lệ |
| Muốn kiểm soát nghiêm ngặt BSON ObjectId | `@MongoId ObjectId id` và chuyển đổi ở ranh giới API | Kiểu Java thể hiện rõ yêu cầu; không chấp nhận String tùy ý |
| Mã SKU, email hoặc tên có thể thay đổi | Thường nên để ở trường riêng, index nếu cần | `_id` là định danh ổn định và không thể cập nhật trực tiếp |

Lưu ý: `ObjectId` không phải quyền truy cập và cũng không phải bí mật. Không dựa vào việc ID khó đoán để thay thế kiểm tra **authentication/authorization**. Trong hệ thống nhiều tenant, tra cứu theo ID thường cần kèm điều kiện tenant hoặc kiểm tra quyền.

## 4. Ví dụ xuyên suốt: ID String cho khách hàng

Ta muốn collection `customers` lưu ID chuỗi nguyên dạng, kể cả khi ID do hệ thống đối tác gửi tới trông giống ObjectId. Dùng entity `Customer` với `@MongoId String id` ở mục 2.2.

Repository:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {

    List<Customer> findByLoyaltyLevelGreaterThanEqual(int level);
}
```

Service lưu và đọc:

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer createSample() {
        return repository.save(
                new Customer("507f1f77bcf86cd799439011", "Lan", 2)
        );
    }

    public Customer find(String id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy khách hàng"));
    }
}
```

MongoDB sẽ có document tương ứng:

```javascript
{
  _id: "507f1f77bcf86cd799439011", // BSON String
  name: "Lan",
  loyaltyLevel: 2
}
```

Thao tác sau trong `mongosh` phân biệt rõ cách lưu:

```javascript
db.customers.findOne({ _id: "507f1f77bcf86cd799439011" });
// Tìm được document đã lưu bằng @MongoId String.

db.customers.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
// Không tìm được cùng document nếu _id là BSON String.
```

`MongoRepository<Customer, String>` khai báo **kiểu ID của mô hình Java**. Nó không bắt buộc `_id` ở database phải là BSON String trong mọi entity; annotation mapping mới xác định quy tắc chuyển đổi. Repository cũng không tạo thêm unique index khác vì MongoDB đã có unique index cho `_id`.

### 4.1. Truy vấn động với `MongoTemplate`

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class CustomerLookup {
    private final MongoTemplate mongoTemplate;

    public CustomerLookup(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Customer findById(String customerId) {
        Query query = Query.query(Criteria.where("id").is(customerId));
        return mongoTemplate.findOne(query, Customer.class);
    }
}
```

Khi nhận `Customer.class`, `MongoTemplate` biết metadata mapping của entity. Tiêu chí `Criteria.where("id")` được ánh xạ tới `_id`; quy tắc `@MongoId` giúp giá trị tham số được biểu diễn đúng với kiểu BSON đã chọn.

**Phân biệt:** khi dùng trực tiếp Java Driver (chẳng hạn `MongoCollection<Document>`), Spring Data **không tham gia chuyển đổi query**. Code driver phải tự gửi đúng BSON type:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

// 'collection' là MongoCollection<Document> đã lấy từ MongoDatabase.
Document found = collection.find(
        Filters.eq("_id", "507f1f77bcf86cd799439011")
).first();
```

Nếu dữ liệu thực là BSON ObjectId, driver cần đối tượng `new ObjectId("507f1f77bcf86cd799439011")` làm giá trị filter. Sự khác biệt giữa query qua Spring Data và query bằng Java Driver là lý do phải kiểm tra định dạng BSON thực tế khi gặp lỗi.

## 5. Ví dụ: ID chuỗi Java nhưng lưu BSON ObjectId

Trong một collection sự kiện, ứng dụng muốn lưu `_id` dạng ObjectId nhưng vẫn nhận/đọc chuỗi hex ở tầng service. Dùng `AuditEvent` của mục 2.3:

```java
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import org.springframework.data.mongodb.core.MongoTemplate;

@Service
public class AuditEventService {
    private final MongoTemplate mongoTemplate;

    public AuditEventService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public AuditEvent append(String hexId, String action) {
        if (hexId == null || !ObjectId.isValid(hexId)) {
            throw new IllegalArgumentException("ID phải là 24 ký tự hex");
        }
        return mongoTemplate.insert(
                new AuditEvent(hexId, action, Instant.now())
        );
    }
}
```

Điều kiện `ObjectId.isValid` giúp từ chối dữ liệu không đúng định dạng trước khi gọi Spring Data. Nếu ID được tạo bởi ứng dụng, cũng có thể dùng `new ObjectId().toHexString()` để tạo một định danh mới rồi truyền vào phương thức.

Khi đã lưu, truy vấn ở `mongosh` sử dụng **ObjectId**, không dùng chuỗi:

```javascript
db.auditEvents.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});

db.auditEvents.aggregate([
  { $match: { _id: ObjectId("507f1f77bcf86cd799439011") } },
  { $project: { action: 1, bsonIdType: { $type: "$_id" } } }
]);
// bsonIdType dự kiến: "objectId"
```

Mã Java ở ví dụ này sử dụng `String` làm ID theo giao diện ứng dụng, còn BSON lưu `ObjectId` nhờ `@MongoId(FieldType.OBJECT_ID)`. Nếu yêu cầu kiểu mạnh hơn, có thể thiết kế entity với `@MongoId ObjectId id` và chỉ chuyển ObjectId ↔ chuỗi ở Controller/DTO.

## 6. Ảnh hưởng tới insert, save, upsert và cập nhật

### 6.1. Insert và ID thiếu

Với `insert`, ứng dụng có thể cấp ID trước hoặc để cơ chế sinh ID của driver/server và mapping framework xử lý khi trường ID được hỗ trợ. **`@MongoId` chủ yếu điều khiển cách ánh xạ kiểu ID; nó không phải annotation tự sinh số thứ tự và không tự đặt quy tắc ID nghiệp vụ.**

Trong các ví dụ cần chắc chắn kiểu ID, hãy chủ động cung cấp giá trị ID hợp lệ trước khi insert. Với ID chuỗi nghiệp vụ, xây chính sách tạo ID rõ ràng; với `ObjectId`, có thể sinh ở ứng dụng hoặc dùng cơ chế mặc định phù hợp, rồi kiểm tra lại kiểu/giá trị.

### 6.2. `save` và `upsert` dựa vào ID hiện có

`MongoRepository.save` hoặc `MongoTemplate.save` có thể tạo mới hoặc cập nhật document tùy trạng thái entity và định danh. Khi đã có document dùng `_id` là String mà mapping mới gửi filter `_id` dưới dạng ObjectId, truy vấn cập nhật có thể **không khớp document cũ**.

Một tình huống nguy hiểm:

1. Database cũ có `_id: "507f1f77bcf86cd799439011"` (**String**).
2. Code được đổi từ `@MongoId String id` sang `@MongoId(FieldType.OBJECT_ID) String id`.
3. Request tải/lưu ID đó theo mapping mới có thể truy vấn `_id` bằng **ObjectId**, nên không tìm được document String cũ.
4. Nếu thao tác có ngữ nghĩa tạo mới/upsert, hệ thống có nguy cơ sinh thêm document với BSON ObjectId dù giá trị biểu diễn hex giống nhau.

Vì vậy, **đổi annotation không phải là migration dữ liệu**. Kiểm tra các lệnh thực tế và trạng thái lưu trước khi triển khai.

### 6.3. Không đổi `_id` trực tiếp bằng update

MongoDB không cho cập nhật giá trị `_id` của một document đã tồn tại theo cách update thông thường. Muốn đổi biểu diễn từ String sang ObjectId, cần một **quy trình di trú có kiểm soát** (tạo document mới với ID đích, cập nhật tham chiếu liên quan, xác minh, rồi xử lý document cũ), tránh tự ý dùng `$set` lên `_id`.

`@Version` (optimistic locking) và `@MongoId` giải quyết hai vấn đề khác nhau: `@Version` theo dõi trạng thái phiên bản khi ghi, còn `@MongoId` điều khiển cách ánh xạ định danh. Không dùng `@Version` để chữa lỗi query sai kiểu `_id`.

## 7. Kiểm tra kiểu BSON thực lưu và lỗi tìm ID

### 7.1. Quan sát bằng `mongosh`

Giả sử đã đăng nhập vào **database thử nghiệm** và có collection `customers`:

```javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      bsonIdType: { $type: "$_id" }
    }
  },
  { $limit: 20 }
]);
```

Trường `bsonIdType` sẽ có giá trị như `"string"` hoặc `"objectId"`. Có thể thống kê cả collection để tìm dữ liệu trộn kiểu:

```javascript
db.customers.aggregate([
  { $group: { _id: { $type: "$_id" }, total: { $sum: 1 } } },
  { $sort: { total: -1 } }
]);
```

Nếu xuất hiện cả `string` và `objectId`, hãy xác định nguyên nhân ở quy tắc mapping, lịch sử import/migration hoặc dữ liệu do Java Driver và Spring Data ghi theo những quy ước khác nhau. Đừng chuyển đổi hàng loạt khi chưa biết collection khác đang tham chiếu theo loại nào.

### 7.2. Quan sát bằng Java Driver

Kiểm tra trực tiếp dữ liệu raw trong môi trường test giúp xác nhận mapping hoạt động đúng:

```java
import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

// 'mongoTemplate' được inject trong test hoặc service dùng để chẩn đoán.
Document rawStringId = mongoTemplate.getCollection("customers")
        .find(eq("_id", "507f1f77bcf86cd799439011"))
        .first();

Document rawObjectId = mongoTemplate.getCollection("auditEvents")
        .find(eq("_id", new ObjectId("507f1f77bcf86cd799439011")))
        .first();

if (rawStringId != null) {
    System.out.println(rawStringId.get("_id") instanceof String);
}
if (rawObjectId != null) {
    System.out.println(rawObjectId.get("_id") instanceof ObjectId);
}
```

Đoạn code trên chỉ kiểm tra kiểu dữ liệu của ID; không in toàn bộ document chứa thông tin nhạy cảm trong log production. Java Driver làm việc với BSON trực tiếp, giúp tách bạch vấn đề lưu trữ khỏi tầng mapping của Spring Data.

### 7.3. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `findById` không thấy document nhưng `mongosh` có dữ liệu | Query dùng ObjectId trong khi `_id` thật là String, hoặc ngược lại | Đọc BSON type bằng `$type`, so với annotation/converter; sửa mapping hoặc di trú có kiểm soát |
| Chỉ các ID 24-hex không truy vấn được | `@Id String` chuyển đổi chúng thành ObjectId, các chuỗi khác giữ String | Chọn quy ước nhất quán; cân nhắc `@MongoId String` nếu ID nghiệp vụ phải nguyên dạng |
| Có hai document nhìn như cùng ID khi xuất sang text | Một document String và một document ObjectId | Kiểm tra type, không so bằng chuỗi hiển thị; lập kế hoạch hợp nhất/migration nếu cần |
| Lưu ID không hợp lệ nhưng không báo lỗi | `FieldType.OBJECT_ID` không phải validator nghiêm ngặt cho mọi đầu vào | Kiểm tra format ở boundary, hoặc dùng `ObjectId` trực tiếp làm kiểu Java |
| `save` tạo document khác thay vì cập nhật | ID được ánh xạ sang BSON type khác với dữ liệu cũ | Xem query ghi, ID thực lưu, ràng buộc unique và lịch sử thay annotation |
| Tham chiếu từ order tới customer không tìm thấy | `customerId` và `customers._id` khác kiểu | Thống nhất cả hai đầu và converter/lookup; kiểm thử với document thực |
| Cùng ID ở các collection khác nhau | `_id` chỉ duy nhất trong từng collection | Không giả định tính duy nhất toàn database; xác định namespace/collection |

## 8. ID, tham chiếu, index và aggregation

### 8.1. Tham chiếu logic phải cùng kiểu

Giả sử `orders.customerId` lưu chuỗi `"507f1f77bcf86cd799439011"` nhưng `customers._id` là BSON ObjectId. Một `$lookup` theo hai trường này **không tự đổi chuỗi thành ObjectId**:

```javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
```

Kết quả `customer` có thể là mảng rỗng dù chuỗi hex trông giống nhau. Giải pháp bền vững là **thiết kế cùng kiểu BSON cho khóa liên kết** hoặc xử lý ánh xạ một cách tường minh; `@DocumentReference`/`@DBRef` cũng không loại bỏ yêu cầu bảo đảm kiểu và quy tắc tham chiếu phù hợp.

### 8.2. Index trên `_id` không giải quyết mọi truy vấn

MongoDB tự có index cho `_id`; không cần thêm một index `{ _id: 1 }` chỉ vì dùng `@MongoId`. Tuy nhiên các truy vấn theo `email`, `customerId`, `createdAt` hoặc aggregation vẫn cần đánh giá index riêng.

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "CUS-1001" })
  .sort({ createdAt: -1 })
  .limit(20);
```

Index ghép có thể hỗ trợ bộ lọc theo `customerId` và sắp xếp theo `createdAt`. Khi truy vấn chậm, sử dụng `explain("executionStats")` trên dữ liệu đại diện; đừng kết luận nguyên nhân chỉ từ việc ứng dụng dùng String hay ObjectId.

### 8.3. Transaction không sửa lỗi sai kiểu ID

Nếu cần thay đổi nhiều document, Spring Data MongoDB có thể phối hợp transaction trên MongoDB deployment hỗ trợ. Tuy nhiên transaction không tự biến `"507..."` thành `ObjectId("507...")`, không sửa tham chiếu sai kiểu và không làm `_id` trở thành mutable. Quy tắc ánh xạ vẫn phải đúng trước khi thiết kế thao tác nguyên tử.

Với reactive access, `ReactiveMongoRepository` hoặc `ReactiveMongoTemplate` vẫn dùng metadata ID của Spring Data và gửi thao tác qua Reactive Streams Driver. Reactive giúp mô hình I/O không chặn nhưng không thay đổi nguyên tắc so sánh BSON type.

## 9. Di trú khi đã chọn sai kiểu `_id`

Giả sử collection lịch sử lưu `_id` là BSON String nhưng phiên bản ứng dụng mới muốn sử dụng BSON ObjectId. Cách làm an toàn cần **thiết kế trước khi chạy trên dữ liệu thật**:

1. **Khảo sát:** thống kê các loại BSON thực tế, số document, tỷ lệ ID có thể chuyển đổi, duplicate về mặt biểu diễn và các collection đang tham chiếu tới ID.
2. **Quy định chuẩn mới:** quyết định collection nào sẽ lưu String, collection nào sẽ lưu ObjectId; không dựa đơn thuần vào cách ID hiển thị trong JSON.
3. **Tạo công cụ/tiến trình di trú có kiểm thử:** chuyển từng document theo ánh xạ xác định; kiểm tra trường hợp chuỗi không phải ObjectId hợp lệ, lỗi unique và tham chiếu.
4. **Cập nhật các mối liên kết:** trường như `orders.customerId`, dữ liệu cache, event và API cần được rà soát; khi đổi ID, các tham chiếu liên quan phải thống nhất cùng kiểu.
5. **Chọn chiến lược chuyển tiếp:** có thể dùng collection mới và ghi/đọc tương thích trong thời gian chuyển tiếp; tránh chuyển đổi ngầm trong request mà không có quan sát.
6. **Xác minh và triển khai:** đối chiếu số record, khóa liên kết, truy vấn, index, dữ liệu không tìm thấy và kế hoạch rollback trước khi chuyển lưu lượng hoàn toàn.

**Không dùng update thông thường để đổi `_id` tại chỗ.** MongoDB xem `_id` là immutable. Việc sao chép/di trú có thể ảnh hưởng unique constraint và transaction; cần chạy trong môi trường kiểm thử trước, ghi nhận mapping ID cũ → mới và chỉ xử lý document cũ sau khi xác minh.

Nếu hệ thống đã dùng một quy ước ID chuỗi ổn định, nhiều khi **giữ nguyên String và dùng `@MongoId`** ít rủi ro hơn chuyển toàn bộ sang ObjectId. Quyết định nên dựa vào yêu cầu tích hợp và hệ thống dữ liệu đang có.

## 10. Kiểm thử mapping với MongoDB thật

Để xác nhận `@MongoId` hoạt động đúng, nên có kiểm thử tích hợp sử dụng MongoDB thực được cô lập, chẳng hạn `@DataMongoTest` kết hợp Testcontainers trong môi trường phù hợp. Unit test chỉ mock repository không thể chứng minh giá trị `_id` đã được mã hóa thành kiểu BSON mong muốn.

Một ma trận kiểm thử tối thiểu:

| Ca kiểm thử | Dữ liệu đầu vào | Kỳ vọng |
| --- | --- | --- |
| String nguyên dạng | `Customer` với ID `"CUS-1001"` | `_id` BSON String; tìm bằng chuỗi thành công |
| String trông như ObjectId | `Customer` với ID `"507f1f77bcf86cd799439011"` | Vẫn lưu BSON String với `@MongoId` mặc định |
| Yêu cầu ObjectId hợp lệ | `AuditEvent` với `@MongoId(FieldType.OBJECT_ID)` và ID 24-hex | `_id` BSON ObjectId; query bằng ObjectId thành công |
| ID không hợp lệ | Chuỗi rỗng, ký tự không phải hex hoặc sai độ dài | Validation của service từ chối trước insert |
| Truy vấn bằng kiểu ngược | Tìm document String bằng BSON ObjectId | Không khớp document String |
| Dữ liệu cũ khác kiểu | Đọc document trước/sau đổi mapping | Phát hiện sai khác, không âm thầm cập nhật nhầm |

Ví dụ assertion trong một test đã được cấu hình `MongoTemplate` và database trống:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class MongoIdMappingTest {

    @Autowired MongoTemplate template;

    @Test
    void stringIdKeepsBsonString() {
        String id = "507f1f77bcf86cd799439011";
        template.insert(new Customer(id, "Lan", 2));

        Document raw = template.getCollection("customers")
                .find(eq("_id", id))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.get("_id")).isInstanceOf(String.class);
    }

    @Test
    void requestedObjectIdUsesBsonObjectId() {
        String id = "507f1f77bcf86cd799439012";
        template.insert(new AuditEvent(id, "LOGIN", java.time.Instant.now()));

        Document raw = template.getCollection("auditEvents")
                .find(eq("_id", new ObjectId(id)))
                .first();

        assertThat(raw).isNotNull();
        assertThat(raw.get("_id")).isInstanceOf(ObjectId.class);
    }
}
```

Các entity `Customer` và `AuditEvent` được định nghĩa ở ví dụ trước và cần nằm trong vùng mà test có thể truy cập/đăng ký mapping. `@DataMongoTest` cung cấp test slice, nhưng **cần cấu hình kết nối tới MongoDB test instance thực**; annotation riêng lẻ không tự tạo MongoDB Server cho mọi dự án. Không trỏ test sang database production.

## 11. Tóm tắt quyết định

Hãy trả lời tuần tự:

1. ID này là **mã nghiệp vụ** cần giữ nguyên, hay **ID kỹ thuật** do hệ thống MongoDB sinh ra?
2. BSON `_id` phải là **String** hay **ObjectId** theo dữ liệu hiện có và các hệ thống đang tích hợp?
3. Nếu dùng String, chuỗi 24-hex có phải giữ nguyên kiểu String trong database không?
4. Nếu dùng ObjectId, đã xác thực ID đầu vào và thống nhất cách chuyển đổi ở ranh giới API chưa?
5. Repository, `MongoTemplate`, Java Driver và các trường tham chiếu có **cùng quy ước BSON type** không?
6. Đã kiểm tra loại `_id` thực lưu, hành vi `findById`/`save` và dữ liệu cũ bằng test tích hợp chưa?

**Quy tắc ghi nhớ:** `@Id String` có thể chuyển chuỗi hex hợp lệ sang BSON ObjectId theo quy tắc mặc định; `@MongoId String` giúp giữ ID nguyên dạng String; `@MongoId(FieldType.OBJECT_ID) String` cho phép yêu cầu ObjectId khi có thể chuyển đổi. **Chọn một quy ước rõ ràng cho từng collection, kiểm tra kiểu BSON thực tế và đừng xem việc đổi annotation là thao tác di trú dữ liệu.**
