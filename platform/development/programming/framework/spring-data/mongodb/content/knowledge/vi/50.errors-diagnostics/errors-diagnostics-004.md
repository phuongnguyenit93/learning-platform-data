# ObjectId và String không khớp dù ID hiển thị giống nhau

Một lỗi khó nhận ra trong **Spring Data MongoDB** là document tồn tại trong collection, `_id` nhìn trên giao diện giống hệt chuỗi ID mà API nhận được, nhưng `findById(...)` hoặc `MongoTemplate.findOne(...)` lại trả về rỗng. Nguyên nhân phổ biến là **giá trị hiển thị giống nhau nhưng kiểu BSON khác nhau**: một bản ghi dùng `ObjectId`, bản ghi kia lưu `String`.

MongoDB so sánh giá trị dựa trên **kiểu BSON và nội dung**, không dựa trên chuỗi mà công cụ quản trị vẽ ra. Vì vậy, `ObjectId("64b7f37a4e92b315c21d0abc")` và `"64b7f37a4e92b315c21d0abc"` là hai giá trị `_id` khác nhau. Spring Data MongoDB còn có quy tắc chuyển đổi ID giữa Java và BSON, khiến sự khác biệt dễ bị che khuất khi ánh xạ `ObjectId` sang thuộc tính `String` của entity.

Trong chương **Lỗi và chẩn đoán** của module `SPRING_DATA_MONGODB`, ta sẽ truy nguyên từ HTTP ID → repository/`MongoTemplate` → MongoDB driver → BSON, rồi chọn mô hình ID thống nhất, viết test xác nhận và lập kế hoạch chuyển đổi dữ liệu cũ nếu cần.

## 1. Hai ID nhìn giống nhau nhưng không bằng nhau

Ví dụ hai document trong cùng collection `orders`:

```javascript
// Document A: _id là BSON ObjectId (12 byte)
{
  _id: ObjectId("64b7f37a4e92b315c21d0abc"),
  status: "PAID"
}

// Document B: _id là BSON String
{
  _id: "64b7f37a4e92b315c21d0abc",
  status: "NEW"
}
```

Cả hai có thể cùng tồn tại vì unique index mặc định trên `_id` xét các giá trị BSON khác nhau. Một truy vấn chỉ khớp với kiểu được cung cấp:

```javascript
const hex = "64b7f37a4e92b315c21d0abc";

db.orders.findOne({ _id: ObjectId(hex) }); // Chọn Document A
db.orders.findOne({ _id: hex });           // Chọn Document B
```

Không nên diễn giải kết quả này thành “MongoDB lúc tìm ID thì không dùng index”. Index `_id_` vẫn có thể được sử dụng; vấn đề là **khóa tra cứu có kiểu khác khóa được lưu**. Thêm index hoặc ép collation thường không sửa được sự khác nhau giữa `ObjectId` và `String`.

| Thành phần | BSON ObjectId | BSON String |
| --- | --- | --- |
| Giá trị minh họa | `ObjectId("64b7f37a4e92b315c21d0abc")` | `"64b7f37a4e92b315c21d0abc"` |
| Kiểu ở MongoDB | `objectId` | `string` |
| Giá trị BSON | 12 byte nhị phân | Chuỗi UTF-8, độ dài lưu trữ riêng |
| Java thường dùng | `org.bson.types.ObjectId` | `java.lang.String` |
| Truy vấn raw qua driver | `Filters.eq("_id", new ObjectId(hex))` | `Filters.eq("_id", hex)` |
| Khi xuất JSON mở rộng | `{"$oid":"64b7..."}` | `"64b7..."` |

Biểu diễn `{"$oid":"..."}` là quy ước **Extended JSON** để mô tả BSON ObjectId; không tự suy rằng mọi JSON object có khóa `$oid` đều đã được chuyển thành ObjectId trong database. Kiểu thực tế chỉ xác định được khi truy vấn BSON hoặc dùng công cụ/codec có hỗ trợ Extended JSON đúng cách.

## 2. Vì sao Spring Data MongoDB dễ gây nhầm lẫn?

### 2.1. Quy tắc ngầm của `@Id String`

Giả sử entity:

```java
package example.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
        @Id String id,
        String status
) {}
```

Spring Data MongoDB có quy tắc ánh xạ đặc biệt cho thuộc tính được đánh dấu `@Id` (hoặc thuộc tính tên `id` được coi là ID theo convention). Khi kiểu Java là `String`, giá trị có thể được chuyển sang BSON `ObjectId` **nếu chuỗi hợp lệ để tạo ObjectId**. Với chuỗi không chuyển được, hệ thống có thể lưu/so sánh bằng String. Cơ chế cụ thể phụ thuộc loại mapping, converter và cách gọi API; không nên đoán kiểu BSON chỉ từ Java field `String`.

Ví dụ:

```java
repository.save(new Order("64b7f37a4e92b315c21d0abc", "PAID"));
```

Với `@Id String` và cấu hình chuyển đổi mặc định, giá trị ID ở trên **có thể được ghi thành BSON ObjectId**. Khi đọc lại, Spring Data có thể ánh xạ giá trị `ObjectId` thành Java `String`, khiến log `order.id()` chỉ hiển thị chuỗi hex và che đi kiểu gốc.

Ngược lại, một document được import hoặc ghi bằng raw driver với `_id` là String 24 ký tự hex có thể không được tìm thấy qua repository đang chuyển điều kiện ID thành ObjectId. Cần xác nhận hành vi của **đúng lớp mapping và phương thức** đang được ứng dụng sử dụng.

### 2.2. `@MongoId` cho phép chỉ rõ kiểu ID mong muốn

Nếu chủ đích của ứng dụng là lưu **BSON String**, có thể dùng annotation Spring Data MongoDB:

```java
package example.orders;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "external_orders")
public record ExternalOrder(
        @MongoId(FieldType.STRING) String id,
        String status
) {}
```

Trong trường hợp này, `@MongoId(FieldType.STRING)` thể hiện hợp đồng lưu `_id` ở kiểu String kể cả khi giá trị gồm đúng 24 ký tự hex. Một entity tương ứng có thể dùng `MongoRepository<ExternalOrder, String>`.

Nếu ứng dụng xác định ID là ObjectId, dùng kiểu Java `ObjectId` trực tiếp thường rõ ràng hơn:

```java
package example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "object_orders")
public record ObjectIdOrder(
        @Id ObjectId id,
        String status
) {}
```

Repository sử dụng `MongoRepository<ObjectIdOrder, ObjectId>`. Khi ID đến từ path parameter HTTP (thường là String), tầng API cần validate rồi chuyển sang `ObjectId` **một cách tường minh**. Điều này tránh tình trạng một chuỗi Java bị hiểu theo hai kiểu lưu trữ khác nhau.

### 2.3. So sánh ba mô hình

| Entity | Kiểu Java | Kiểu `_id` được kỳ vọng | Điều cần lưu ý |
| --- | --- | --- | --- |
| `@Id String id` | String | Có chuyển đổi ngầm sang ObjectId khi phù hợp | Dễ đọc nhầm dữ liệu nhập từ hệ thống khác |
| `@MongoId(FieldType.STRING) String id` | String | BSON String | Không tự hợp nhất document có ObjectId cũ |
| `@Id ObjectId id` | ObjectId | BSON ObjectId | API nên parse/validate ID tại boundary |

Chọn mô hình ID dựa trên contract lưu trữ đã xác định; tránh đổi annotation vội vàng để “cho query chạy” mà chưa kiểm tra dữ liệu thực tế. Đổi mapping có thể khiến những document trước đây được tìm thấy trở thành không tìm thấy.

## 3. Chẩn đoán theo từng tầng: request, Java, BSON

Khi endpoint `GET /orders/{id}` trả 404 dù document tồn tại, kiểm tra có thứ tự:

1. **Đầu vào HTTP:** ghi nhận request ID đã qua validation; xác định có trim, đổi chữ hoa/thường, thêm prefix hoặc decode URL ở tầng API hay không.
2. **Entity và repository:** xem thuộc tính ID có `@Id`, `@MongoId` hay mapping custom; repository khai báo generic ID là `String` hay `ObjectId`.
3. **Đường gọi:** `repository.findById(...)`, `MongoTemplate.findById(...)` và driver `collection.find(...)` có thể đi qua những đường chuyển đổi khác nhau.
4. **Giá trị BSON thực:** đọc document bằng raw driver và xem kiểu `_id`; không chỉ dựa vào chuỗi in trên UI.
5. **Phạm vi lọc:** đảm bảo tenant, status, soft-delete flag và quyền truy cập cũng khớp. Mismatch ID không phải lý do duy nhất làm query trả rỗng.
6. **Việc ghi/import:** tìm nơi document được tạo: Spring repository, `MongoTemplate`, shell script, ETL hay ứng dụng ngôn ngữ khác.

### 3.1. Đọc trực tiếp bằng `mongosh`

Trên **database kiểm thử** có dữ liệu mẫu:

```javascript
const hex = "64b7f37a4e92b315c21d0abc";

// Khác nhau ở kiểu BSON của giá trị truy vấn:
db.orders.findOne({ _id: ObjectId(hex) });
db.orders.findOne({ _id: hex });

// Xem kiểu BSON trong chính kết quả trả về:
db.orders.aggregate([
  { $match: { _id: { $in: [ObjectId(hex), hex] } } },
  { $project: { _id: 1, idType: { $type: "$_id" }, status: 1 } }
]);
```

Nếu cả hai truy vấn `findOne` đều trả document, collection đang chứa **hai bản ghi có khóa logic cùng dạng hex nhưng kiểu BSON khác nhau**. Nếu chỉ một truy vấn trả kết quả, ta có bằng chứng về kiểu thực tế và có thể đối chiếu đường ánh xạ của Spring Data.

Muốn kiểm kê phân bố kiểu `_id` cho cả collection, có thể chạy aggregation:

```javascript
db.orders.aggregate([
  { $group: { _id: { $type: "$_id" }, documents: { $sum: 1 } } },
  { $sort: { documents: -1 } }
]);
```

Aggregation này có thể cần đọc nhiều document, vì vậy hãy thử trên collection nhỏ hoặc bản sao test trước; trên production collection lớn cần lên kế hoạch tài nguyên/thời điểm chạy. Dùng mẫu representative và thống kê có kiểm soát thay vì quét toàn bộ vào giờ cao điểm.

### 3.2. Dùng raw Java Driver để phân biệt kiểu

`MongoTemplate.getCollection(...)` trả về MongoDB Java Driver collection, cho phép quan sát BSON gốc:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

String hex = "64b7f37a4e92b315c21d0abc";
MongoCollection<Document> collection =
        mongoTemplate.getCollection("orders");

Document byObjectId = collection
        .find(Filters.eq("_id", new ObjectId(hex))).first();
Document byStringId = collection
        .find(Filters.eq("_id", hex)).first();

if (byObjectId != null) {
    Object key = byObjectId.get("_id");
    System.out.println(key.getClass().getSimpleName()); // ObjectId
}
if (byStringId != null) {
    Object key = byStringId.get("_id");
    System.out.println(key.getClass().getSimpleName()); // String
}
```

Đây là code chẩn đoán dùng dữ liệu giả lập, không nên in tùy tiện ID thật hoặc document chứa dữ liệu nhạy cảm vào log vận hành. Nếu cần quan sát production, dùng loại BSON, tên collection, trace ID và mã lỗi; tránh log toàn bộ BSON/URI/credentials.

Raw driver `Filters.eq("_id", hex)` giữ kiểu `String`; raw driver `Filters.eq("_id", new ObjectId(hex))` dùng kiểu `ObjectId`. Khi query đi qua Spring Data mapping, ID có thể được chuyển theo entity metadata. Vì vậy **không dùng kết quả raw driver để suy rằng repository phải gửi đúng cùng BSON nếu chưa kiểm tra mapping**.

### 3.3. Đừng chỉ so sánh JSON hiển thị

Một API thường serializes `ObjectId` thành chuỗi hex, ví dụ `"id": "64b7..."`. Hai bản ghi dùng kiểu BSON khác nhau có thể trở nên không phân biệt được sau bước chuyển sang JSON. Những dấu hiệu như case khác nhau, khoảng trắng, `null` hoặc tiền tố cũng gây nhầm lẫn riêng; cần phân biệt chúng khỏi mismatch BSON type.

Nếu log ghi “found ID X” từ Java field `String`, điều đó chưa chứng minh `_id` được lưu là BSON String. Hãy kiểm tra đúng giá trị trong BSON và lệnh tìm kiếm thực tế.

## 4. Truy vấn đúng theo một hợp đồng ID nhất quán

### 4.1. Trường hợp chuẩn hóa về BSON ObjectId

Khi ID trong database phải là ObjectId, định nghĩa entity `ObjectIdOrder` như trên, repository:

```java
package example.orders;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ObjectIdOrderRepository
        extends MongoRepository<ObjectIdOrder, ObjectId> {}
```

Ở boundary HTTP, nhận String rồi parse có kiểm soát:

```java
import java.util.Optional;
import org.bson.types.ObjectId;

public Optional<ObjectIdOrder> findOrderByPathId(String pathId) {
    if (pathId == null || !ObjectId.isValid(pathId)) {
        return Optional.empty(); // Controller có thể trả HTTP 400 cho ID sai định dạng
    }
    return objectIdOrderRepository.findById(new ObjectId(pathId));
}
```

`ObjectId.isValid(...)` dùng để kiểm tra biểu diễn hex của ObjectId trước khi tạo đối tượng. Trong API có phân quyền, vẫn phải xác nhận tenant/owner của document; `findById` đơn thuần không gắn giới hạn quyền. Dùng filter có tenant khi truy vấn dữ liệu nhiều tenant.

Với `MongoTemplate`, khi entity ID là `ObjectId`, có thể truy vấn:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ObjectId objectId = new ObjectId(pathId); // Đã validate phía trên
Query query = Query.query(Criteria.where("_id").is(objectId));
ObjectIdOrder order =
        mongoTemplate.findOne(query, ObjectIdOrder.class);
```

### 4.2. Trường hợp ID phải là BSON String

Nếu ID do hệ thống ngoài cấp và **luôn** được lưu là String, dùng `@MongoId(FieldType.STRING)` và repository với generic ID `String`:

```java
package example.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface ExternalOrderRepository
        extends MongoRepository<ExternalOrder, String> {}
```

Lúc này `findById("64b7f37a4e92b315c21d0abc")` cần truy vấn theo chuỗi lưu trữ, không tự coi là ObjectId chỉ vì đủ 24 ký tự hex. Với truy vấn trực tiếp raw driver, dùng `Filters.eq("_id", pathId)` và bảo toàn kiểu String.

**Lưu ý tính chính xác:** Nếu dữ liệu có `_id` kiểu ObjectId cũ nhưng entity mới chỉ tìm theo String, entity mới không tự chuyển dữ liệu lịch sử. Cần một kế hoạch đọc tương thích/migration được kiểm soát.

### 4.3. Đừng dùng `findById(String)` như một phép dò cả hai kiểu

Việc cố gọi repository tìm String trước rồi chuyển ObjectId sau có thể trở thành hành vi khó dự đoán, nhất là khi `@Id String` kích hoạt implicit conversion hoặc cả hai bản ghi tồn tại.

Nếu cần **đọc tạm thời** collection hỗn hợp và ID đầu vào là 24 ký tự hex hợp lệ, có thể thiết kế adapter raw driver truy vấn hai dạng, rồi xử lý trùng rõ ràng:

```java
import com.mongodb.client.model.Filters;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;

public Document readLegacyOrder(
        String hex, String authenticatedTenantId) {
    if (hex == null || !ObjectId.isValid(hex)) {
        throw new IllegalArgumentException("Expected ObjectId hex");
    }

    var filter = Filters.and(
            Filters.eq("tenantId", authenticatedTenantId),
            Filters.or(
                    Filters.eq("_id", new ObjectId(hex)),
                    Filters.eq("_id", hex)));

    List<Document> matches = mongoTemplate.getCollection("orders")
            .find(filter)
            .limit(2)
            .into(new ArrayList<>());

    if (matches.size() > 1) {
        throw new IllegalStateException("Ambiguous logical order ID");
    }
    return matches.isEmpty() ? null : matches.get(0);
}
```

Đây là **adapter migration tạm thời**, giả định ID external được biểu diễn bằng ObjectId hex, có tenant ID lấy từ phiên đăng nhập đã được xác thực và hệ thống có quy tắc xử lý document trùng. Không áp dụng mẫu này cho mọi ID String tùy ý, không bỏ tenant scope và không chọn bản ghi đầu tiên khi cùng ID logic tồn tại ở cả hai kiểu. Nếu business ID không phải hex ObjectId, đường đọc String cần được định nghĩa riêng.

Trong hệ thống thực tế, để trả về một entity nghiệp vụ chung từ adapter trên cần ánh xạ/chuẩn hóa document sau khi xác nhận bản ghi và quyền. Không gọi `save(...)` trực tiếp trên entity ánh xạ một phần vì có thể làm mất field không khai báo.

## 5. Những bẫy thường gặp khi import, mapping và join

### 5.1. Ghi dữ liệu bằng nhiều đường khác nhau

Các nguồn ghi phổ biến:

| Nguồn ghi | Hành vi có thể phát sinh | Việc cần kiểm tra |
| --- | --- | --- |
| Spring Data entity `@Id String` | Có implicit ObjectId conversion nếu ID hợp lệ | Converter và BSON thực |
| Entity `@MongoId(FieldType.STRING)` | Lưu String đúng hợp đồng | Có dữ liệu cũ kiểu ObjectId không? |
| Spring Data entity `@Id ObjectId` | Lưu ObjectId | API đã parse ID đúng chưa? |
| `mongosh` | Phụ thuộc cú pháp `ObjectId(...)` hay chuỗi | Script seed/import |
| Raw Java Driver | Phụ thuộc kiểu Java của `Filters.eq` và `Document` | Xem `get("_id").getClass()` |
| ETL/JSON import | Phụ thuộc Extended JSON/codec và kiểu nguồn | Dữ liệu BSON sau import |

Một job migration có thể giữ nguyên chuỗi `"64b..."` trong `_id`, trong khi writer ứng dụng tạo ra BSON ObjectId. Nếu mọi report chỉ hiển thị ID ở dạng text, sự khác biệt có thể không được phát hiện cho tới khi truy vấn join hoặc repository thay đổi.

### 5.2. `$lookup` không nối nếu khóa khác kiểu

Giả sử `orders.customerId` là String `"64b..."` nhưng `customers._id` là ObjectId tương ứng. Pipeline:

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

có thể tạo mảng `customer: []` vì phép so khớp khóa dùng hai kiểu BSON khác nhau. Trường hợp này thường bị hiểu sai thành “sai collection” hoặc “thiếu index”.

Nếu dữ liệu có hợp đồng String → ObjectId hex rõ ràng, có thể kiểm tra và chuyển **ở bước migration hoặc biểu thức aggregation được kiểm soát**, ví dụ dùng `$convert` với `onError`/`onNull` để xử lý ID không hợp lệ. Tuy nhiên, phép chuyển kiểu trong pipeline có thể làm giảm khả năng dùng index hoặc tăng công việc trên tập dữ liệu lớn; chọn sửa mô hình lưu trữ lâu dài thay vì phụ thuộc chuyển đổi runtime ở mọi truy vấn.

### 5.3. `String.equals(...)` không chứng minh BSON bằng nhau

Ở Java, `String.valueOf(raw.get("_id"))` có thể in ra những giá trị tương tự với chuỗi hex từ API. Chuyển cả hai về String để so sánh trong log chỉ chứng minh phần **biểu diễn**, không phản ánh kiểu BSON hoặc cách index MongoDB so sánh.

Muốn kiểm chứng, quan sát `raw.get("_id") instanceof ObjectId` hoặc `instanceof String` trong raw BSON, cùng điều kiện truy vấn driver/Spring Data đã gửi.

## 6. Chuyển dữ liệu trộn kiểu về một chuẩn

Trước khi migration, xác định **chuẩn đích**: ObjectId hay BSON String. Không có lựa chọn đúng cho mọi hệ thống. ObjectId phù hợp khi database tạo ID hoặc domain chấp nhận ObjectId; String có thể phù hợp cho mã định danh do một hệ thống ngoài kiểm soát, kể cả mã chứa ký tự không phải hex.

Các bước an toàn:

1. **Kiểm kê:** đo số document có `_id` String/ObjectId, nguồn writer tương ứng, các collection tham chiếu và khả năng tồn tại khóa logic trùng.
2. **Phân loại:** xác định String nào là mã nghiệp vụ thực, String nào chỉ là biểu diễn hex của ObjectId. Không tự ép tất cả String sang ObjectId nếu không có quy tắc hợp lệ.
3. **Chuyển reader:** triển khai lớp đọc tương thích/giám sát để ứng dụng còn đọc được dữ liệu trong khi migration, có chính sách khi tìm ra hai bản ghi cùng logical ID.
4. **Chuyển writer:** đảm bảo mọi producer mới ghi đúng kiểu đích, không còn tạo hai dạng.
5. **Migration và đối soát:** chuyển dữ liệu theo batch được kiểm soát, đối chiếu count, tham chiếu, ràng buộc unique, quyền truy cập và các tác vụ phụ thuộc.
6. **Thu hẹp:** sau khi xác nhận không còn dữ liệu/writer cũ, bỏ adapter chuyển kiểu, metric tạm và những workaround truy vấn không cần thiết.

### 6.1. `_id` là immutable

MongoDB **không cho cập nhật trực tiếp giá trị `_id`** của document đang tồn tại. Không thể sửa kiểu bằng:

```javascript
// KHÔNG phải cách chuyển kiểu _id:
db.orders.updateOne(
  { _id: "64b7f37a4e92b315c21d0abc" },
  { $set: { _id: ObjectId("64b7f37a4e92b315c21d0abc") } }
);
```

Muốn chuyển khóa phải tạo document **mới** với `_id` đúng kiểu và xử lý bản ghi cũ theo kế hoạch có kiểm soát. Việc copy → verify → delete có rủi ro khi writer vẫn ghi, khi có tham chiếu từ collection khác và khi cả hai kiểu đã cùng tồn tại. Cần khóa, điều kiện cập nhật/phiên bản, idempotency và lựa chọn transaction phù hợp nếu thao tác nhiều document yêu cầu nhất quán; transaction MongoDB cần replica set/sharded deployment phù hợp.

Không xóa record cũ trước khi xác minh record mới và mọi tham chiếu liên quan. Chạy thử trên snapshot hoặc môi trường staging, có checkpoint và phương án rollback đã được kiểm chứng.

### 6.2. Không biến mọi ID sang String trong API rồi kết luận database đồng nhất

API có thể nhất quán biểu diễn ID ở dạng text nhưng **contract lưu trữ** vẫn phải rõ kiểu. Nếu chọn ObjectId, tầng application parse ID thành `ObjectId` trước truy vấn. Nếu chọn String, annotate `@MongoId(FieldType.STRING)` và giữ raw String trong BSON. Khi cần tích hợp với hệ thống ngoài, dùng lớp chuyển đổi tại boundary thay vì để entity lưu trữ và JSON response mâu thuẫn kiểu với nhau.

## 7. Kiểm thử lỗi trên MongoDB thật

Mock `MongoRepository` không tái hiện đầy đủ cơ chế Spring Data mapping/BSON. Dùng Testcontainers hoặc MongoDB service dành cho test để kiểm chứng các tình huống.

### 7.1. Dữ liệu mẫu chứng minh khác biệt BSON

Đoạn dưới là phần test Java dùng `MongoTemplate` đã kết nối MongoDB test. Nó không cần Spring Data entity để chứng minh hai kiểu `_id` khác nhau:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;

String hex = "64b7f37a4e92b315c21d0abc";
ObjectId oid = new ObjectId(hex);
MongoCollection<Document> collection =
        mongoTemplate.getCollection("diagnostic_orders");

collection.insertMany(List.of(
        new Document("_id", oid).append("status", "PAID"),
        new Document("_id", hex).append("status", "NEW")));

Document a = collection.find(Filters.eq("_id", oid)).first();
Document b = collection.find(Filters.eq("_id", hex)).first();

assertThat(a).isNotNull();
assertThat(b).isNotNull();
assertThat(a.get("_id")).isInstanceOf(ObjectId.class);
assertThat(b.get("_id")).isInstanceOf(String.class);
```

Các assertion sử dụng AssertJ. Fixture chỉ được chạy trên collection thuộc riêng test; phải cleanup hoặc dùng database mới trước khi test chạy lặp. Kết quả cho thấy unique index trên `_id` không ngăn hai giá trị có BSON type khác nhau.

### 7.2. Test mapping sau khi chọn kiểu

Với entity `ExternalOrder` sử dụng `@MongoId(FieldType.STRING)`, cần assert BSON raw sau khi lưu:

```java
String hex = "64b7f37a4e92b315c21d0abc";
externalOrderRepository.save(new ExternalOrder(hex, "NEW"));

Document stored = mongoTemplate.getCollection("external_orders")
        .find(Filters.eq("_id", hex))
        .first();

assertThat(stored).isNotNull();
assertThat(stored.get("_id")).isInstanceOf(String.class);
assertThat(externalOrderRepository.findById(hex)).isPresent();
```

Với entity `ObjectIdOrder`, tạo `ObjectId` và xác nhận `_id` được lưu là ObjectId. Một test quan trọng khác là seed raw String với cùng 24 ký tự hex vào collection, sau đó quan sát repository dựa trên `@Id String` hoạt động ra sao trong **phiên bản Spring Data đang dùng**. Kết quả giúp kiểm chứng quy tắc chuyển đổi implicit khi read/write/query.

### 7.3. Ma trận test tối thiểu

| Tình huống | Kỳ vọng |
| --- | --- |
| DB `ObjectId`, query raw `ObjectId` | Tìm thấy |
| DB `ObjectId`, query raw `String` | Không tìm thấy |
| DB `String`, query raw `String` chính xác | Tìm thấy |
| DB `String`, query raw `ObjectId` | Không tìm thấy |
| Cùng text nhưng cả hai BSON type cùng tồn tại | Adapter phát hiện ambiguous ID |
| Entity `@MongoId(FieldType.STRING)` lưu ID 24 hex | BSON String, repository tìm được |
| Entity `@Id ObjectId` với input không phải ObjectId hex | API báo lỗi validation trước truy vấn |
| `$lookup` String → ObjectId | Không tự match như String → String |
| ID đúng nhưng tenant khác | Không được truy xuất dữ liệu |
| Migration chạy lại | Không ghi đè hoặc xóa bản ghi sai |

### 7.4. Không trộn test nghiệp vụ với benchmark

Những test trên xác nhận tính **đúng** của mapping/truy vấn. Khi chẩn đoán hiệu năng, dùng `explain("executionStats")` và telemetry để theo dõi `totalDocsExamined`, `totalKeysExamined`, command count, network payload và độ trễ. Tuy nhiên, đối với lỗi ID khác BSON type, vấn đề cần giải quyết trước tiên là **ngữ nghĩa truy vấn và kiểu khóa**, không phải tăng `limit`, thêm index hoặc đổi batch size.

## 8. Các lỗi liên quan và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `findById` rỗng dù UI thấy record | Mismatch BSON ID type | So sánh hai raw query theo String/ObjectId |
| Raw driver tìm thấy nhưng repository không thấy | Mapping `@Id`, `@MongoId` hoặc converter khác | Kiểm tra entity metadata và raw BSON |
| API hiển thị hai bản ghi cùng ID text | String và ObjectId cùng tồn tại | Kiểm tra `$type` của `_id` |
| Lỗi parse ObjectId | ID không phải chuỗi hex 24 ký tự hợp lệ | `ObjectId.isValid(...)` tại boundary |
| `ClassCastException` khi gọi `getString("_id")` | BSON raw là ObjectId | Xem kiểu bằng `get("_id")` trước khi cast |
| `$lookup` ra mảng rỗng | Field local/foreign khác kiểu hoặc không khớp giá trị | Xem kiểu BSON của hai khóa |
| Truy vấn theo ID chậm nhưng có kết quả | Khác vấn đề, như query thêm điều kiện/sort | `explain` và telemetry |
| ID đúng, tenant khác hoặc bị soft-delete | Điều kiện quyền/trạng thái lọc thêm | Kiểm tra filter đầy đủ và authorization |
| Sau đổi annotation thì mất bản ghi cũ | Kiểu BSON được truy vấn đã thay đổi | Kiểm kê collection, test trước/sau mapping |

Một lỗi khác là **chuỗi hex khác chữ hoa/thường**: ObjectId thường được biểu diễn dưới dạng hex chuẩn hóa, còn BSON String lưu nguyên chuỗi và có quy tắc so sánh theo collation. Vấn đề case khác biệt với việc hai kiểu BSON khác nhau; không dùng `toLowerCase()` tùy ý để “chữa” mọi trường hợp mà chưa xác định kiểu và contract ID.

## 9. Quy trình xử lý trong môi trường vận hành

Khi có báo cáo 404 bất thường:

1. Ghi nhận trace ID, collection, loại mapping và dạng ID đã được validation; không đưa toàn bộ document vào log.
2. Trong môi trường được phép, kiểm tra giá trị bằng raw query String và ObjectId, có tenant scope phù hợp.
3. Đối chiếu đường ghi và đường đọc: writer dùng repository, raw driver, shell script hay ETL; xác định nơi hai kiểu bắt đầu trộn.
4. Kiểm tra cấu hình entity và repository ID generic type; nếu có custom `MongoConverter` hoặc `MongoCustomConversions`, đánh giá ảnh hưởng đến ID mapping.
5. Seed đúng hai kiểu trong Testcontainers/service MongoDB và tạo test tái hiện; xác nhận phương án sửa mapping hoặc adapter.
6. Đo số bản ghi lịch sử bị ảnh hưởng, lên kế hoạch migration nếu cần và triển khai reader phù hợp trước khi sửa writer.
7. Theo dõi số lần tìm ID không thấy, số ID sai định dạng, số trường hợp ambiguous và tỷ lệ document còn dùng kiểu cũ.

Metric nên có nhãn cố định (ví dụ `id_bson_type=objectId|string|unknown`), không dùng giá trị ID làm tag. Đảm bảo truy vấn chẩn đoán không bỏ qua kiểm soát tenant/quyền chỉ vì thao tác đang ở chế độ debug.

## 10. Bài tập thực hành

**Bài 1 — Chẩn đoán bằng `mongosh`.** Tạo hai document có cùng chuỗi 24 hex nhưng một `_id` là `ObjectId`, một là String. Viết hai phép `findOne` và một aggregation dùng `$type` để chứng minh chúng khác nhau. Giải thích vì sao unique index `_id_` vẫn cho phép cả hai.

**Bài 2 — So sánh `@Id String` và `@MongoId(FieldType.STRING)`.** Tạo hai entity và repository riêng, lưu một ID 24 ký tự hex, dùng driver đọc lại BSON. Ghi nhận kiểu lưu trữ và kết quả `findById` trong phiên bản Spring Data MongoDB đang dùng.

**Bài 3 — Boundary HTTP.** Tạo endpoint tra cứu đơn với ID lưu dạng ObjectId. Validate path ID, parse thành `ObjectId` rồi query; kiểm thử chuỗi không hợp lệ, document không có và document thuộc tenant khác.

**Bài 4 — Migration hỗn hợp.** Tạo dataset gồm String, ObjectId và một cặp cùng logical ID. Thiết kế adapter đọc tạm, chính sách ambiguous ID, cách chuyển `_id` immutable và kế hoạch đối soát trước khi xóa dữ liệu cũ.

**Bài 5 — `$lookup` và performance.** Seed `orders.customerId` là String và `customers._id` là ObjectId; xác nhận `$lookup` không match. Đề xuất cách đồng nhất schema để query dùng index hiệu quả, rồi đo `explain("executionStats")` trên tập dữ liệu đủ lớn.

**Tiêu chí hoàn thành:** Người học phân biệt được kiểu BSON ObjectId với String dù cùng biểu diễn hex; xác định đường chuyển đổi ID của Spring Data MongoDB; dùng `@Id`, `@MongoId(FieldType.STRING)` và kiểu repository nhất quán; chẩn đoán bằng raw driver/`$type`; và lập kế hoạch migration an toàn khi `_id` không thể cập nhật trực tiếp.
