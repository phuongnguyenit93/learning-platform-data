# Ánh xạ ObjectId, UUID, Decimal128, ngày giờ và giá trị null trong MongoDB Java Driver

Khi ứng dụng Java lưu một đối tượng vào MongoDB, driver không đơn giản chuyển mọi thứ thành JSON string. MongoDB lưu dữ liệu theo **BSON (Binary JSON)**, có các kiểu riêng như `ObjectId`, `Binary`, `Decimal128`, `Date` và `Null`. Java lại có những kiểu như `String`, `UUID`, `BigDecimal`, `Instant`, `LocalDate`, `Date` và các primitive/wrapper types. Nếu ánh xạ sai, dữ liệu có thể bị đọc không ra, truy vấn sai index, mất chính xác tiền tệ, thay đổi giờ hoặc vô tình phân biệt nhầm “chưa có giá trị” với “giá trị null”.

Bài **“Ánh xạ ObjectId, UUID, Decimal128, ngày giờ và giá trị null”** thuộc chương **Java Driver** của module **Database Engine Document MongoDB**. Nội dung hướng tới **MongoDB Java Sync Driver** và các cơ chế codec của BSON; những nguyên tắc về BSON cũng hữu ích khi dùng reactive driver hoặc framework phía trên.

Mục tiêu học:

1. Hiểu **BSON type** là một phần của dữ liệu và tiêu chí matching query.
2. Dùng đúng `ObjectId`, chuỗi hex, `UUID` và các biểu diễn BSON binary.
3. Lưu số thập phân chính xác với `Decimal128`/`BigDecimal` mà không vô tình đưa qua `double`.
4. Ánh xạ BSON Date sang `Date`/`Instant` và xử lý UTC, timezone, nanosecond/millisecond precision.
5. Phân biệt **BSON null**, **field không tồn tại** và **Java null**.
6. Hiểu cách `Document`/`BsonDocument` khác POJO codecs, và khi nào cần cấu hình codec registry.
7. Kiểm tra kiểu dữ liệu thật trước/sau khi lưu, viết filter/update phù hợp và lập kế hoạch migration dữ liệu legacy.

> **Lưu ý phiên bản:** tên API minh họa theo MongoDB Java Sync Driver/BSON driver hiện đại. Java driver, MongoDB server, codec registry và framework có thể khác nhau theo release. Khi sử dụng dependency cụ thể, cần đối chiếu API/tài liệu của chính version đó. Các ví dụ chạy trên database lab, không trực tiếp thay đổi schema dữ liệu production.

## 1. Khác biệt cốt lõi: JSON không mô tả hết BSON

Xét một document MongoDB:

```javascript
{
  _id: ObjectId("65f000000000000000000101"),
  requestId: UUID("b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"),
  price: NumberDecimal("199.90"),
  createdAt: ISODate("2026-11-14T08:15:30.123Z"),
  cancelledAt: null
}
```

Trong đó:

- `_id` là **BSON ObjectId**, không phải một string 24 ký tự.
- `requestId` có thể là **BSON Binary UUID subtype 4**, không phải string UUID. Cách encode chính xác phụ thuộc vào client/representation.
- `price` là **BSON Decimal128**, không phải Java `double`.
- `createdAt` là **BSON DateTime**, một giá trị timestamp theo milliseconds kể từ Unix epoch UTC; MongoDB không lưu tên múi giờ trong kiểu Date.
- `cancelledAt` là **BSON null** vì field có mặt và giá trị là null.

Nếu field `cancelledAt` hoàn toàn vắng mặt thì đó lại là một trạng thái dữ liệu khác.

### BSON có kiểu ngay cả khi UI trông giống chuỗi

Kết quả từ `mongosh` hoặc một công cụ quản trị có thể hiển thị ObjectId, Date, Decimal128 dưới dạng dễ đọc. Nhưng sự thể hiện trên màn hình **không làm chúng thành string**. Truy vấn cùng hình thức ký tự nhưng khác BSON type có thể cho kết quả khác nhau.

Ví dụ:

```javascript
// Tìm _id BSON ObjectId:
db.orders.findOne({
  _id: ObjectId("65f000000000000000000101")
});

// Không tương đương nếu _id thực tế là ObjectId:
db.orders.findOne({
  _id: "65f000000000000000000101"
});
```

MongoDB không mặc nhiên ép chuỗi hex thành ObjectId khi so sánh equality.

## 2. Bảng ánh xạ tổng quan BSON ↔ Java

| Ý nghĩa nghiệp vụ | BSON type | Java type thường dùng | Ghi chú |
| --- | --- | --- | --- |
| ID tự sinh kiểu MongoDB | ObjectId | `org.bson.types.ObjectId` | 12 byte BSON, hiển thị 24 hex chars |
| UUID chuẩn | Binary subtype 4 | `java.util.UUID` | Cấu hình `UuidRepresentation.STANDARD` |
| UUID legacy | Binary subtype 3 | `UUID` với legacy representation cụ thể | Cần biết quy tắc byte order nguồn |
| Tiền/số thập phân chính xác | Decimal128 | `org.bson.types.Decimal128` | BSON decimal 128-bit |
| Số thập phân trong domain Java | Decimal128 theo codec | `java.math.BigDecimal` | Kiểm tra khả năng biểu diễn Decimal128 |
| Thời điểm | DateTime | `java.util.Date` hoặc `java.time.Instant` | Milliseconds UTC, không lưu zone name |
| Ngày lịch không có giờ | Phụ thuộc schema | `java.time.LocalDate` | Chọn convention rõ, không coi là instant |
| Ngày giờ địa phương | Phụ thuộc schema | `LocalDateTime` | Chưa có timezone, cần zone khi chuyển instant |
| Giá trị null hiện hữu | Null | `null` / `BsonNull.VALUE` | Phải phân biệt với field không có |
| Field vắng mặt | Không có phần tử BSON | Không có key trong `Document` | POJO property có thể vẫn là Java null |
| Số nguyên 32-bit | Int32 | `Integer`/`int` | Không giống Int64 |
| Số nguyên 64-bit | Int64 | `Long`/`long` | Đọc đúng codec/type |
| Số chấm động | Double | `Double`/`double` | Không lý tưởng cho số tiền chính xác |

**Cảnh báo:** đây là bảng ánh xạ phổ biến, không phải cam kết mọi codec registry hoặc framework luôn chọn đúng như nhau. Một `Document` chứa giá trị được giải mã qua `DocumentCodec`; một POJO dùng `PojoCodec` và codec của từng property. Custom codecs và annotation có thể đổi behavior.

## 3. Codec là cầu nối giữa BSON và đối tượng Java

**Codec** chịu trách nhiệm encode đối tượng Java thành BSON và decode BSON thành đối tượng Java.

```text
Java object
   |
   v
Codec.encode(...)
   |
   v
BSON trong MongoDB
   |
   v
Codec.decode(...)
   |
   v
Java object
```

**Codec registry** là tập codecs mà driver sử dụng. Các lớp quen thuộc:

- `ObjectIdCodec` xử lý `ObjectId`.
- `UuidCodec` xử lý `UUID` theo `UuidRepresentation`.
- `Decimal128Codec` xử lý `Decimal128`.
- Codec cho `BigDecimal` có thể mã hóa sang Decimal128 trong registry tương thích.
- Java date/time codecs xử lý các kiểu thời gian được hỗ trợ.
- `DocumentCodec` xử lý `org.bson.Document`.
- `PojoCodecProvider` cung cấp codecs cho classes Java được đăng ký/được tự động nhận diện theo cấu hình.

Khi đọc dữ liệu mà gặp lỗi `CodecConfigurationException`, nguyên nhân thường là **không có codec phù hợp**, không nhất thiết là database corrupt.

### Hai phong cách lập trình

**Làm việc trực tiếp với Document:**

```java
MongoCollection<Document> collection =
    database.getCollection("orders");
```

Ứng dụng chủ động chọn những value types đưa vào `Document`, và phải đọc ra đúng type.

**Làm việc với POJO:**

```java
MongoCollection<OrderRecord> collection =
    database.getCollection("orders", OrderRecord.class);
```

Driver phải có codec có thể ánh xạ class/properties. DTO được định nghĩa rõ ràng, nhưng phụ thuộc vào conventions, annotations, getters/setters, constructors và codec registry.

## 4. Thiết lập môi trường Java thực hành

Giả định:

- Java 17+.
- Một MongoDB lab có thể kết nối qua `MONGODB_URI`.
- Dependency `org.mongodb:mongodb-driver-sync` với version phù hợp trong project.
- Không ghi password thật vào repository hoặc log.

Một mẫu kết nối:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

public class MongoConnectionExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("java_bson_mapping_lab");
            System.out.println(database.getName());
        }
    }
}
```

Trong các ví dụ tiếp theo, `collection` hoặc `database` là biến được tạo từ một `MongoClient` còn hoạt động. Không tái sử dụng `MongoCollection` sau khi `MongoClient` đã bị đóng.

## 5. ObjectId là gì?

**BSON ObjectId** là định danh BSON dài **12 byte**, thường hiển thị thành **24 ký tự hex**. MongoDB có thể tự tạo `_id` dạng ObjectId trong nhiều đường ghi nếu ứng dụng không cung cấp giá trị; Java driver cũng có thể tạo trước ID ở phía client.

```java
import org.bson.types.ObjectId;

ObjectId id = new ObjectId();

System.out.println(id.toHexString());
// Ví dụ định dạng: 65f000000000000000000101
```

Giá trị thực từ `new ObjectId()` là mới, **không cố định** như một ví dụ chữ hex.

### Cấu trúc ObjectId

Một ObjectId gồm các phần có ý nghĩa ở cấp byte:

```text
12 bytes:
  4 bytes  timestamp theo giây
  5 bytes  random value đặc trưng process/machine
  3 bytes  counter

Hiển thị:
  24 ký tự hexadecimal
```

ObjectId không phải một chuỗi ngẫu nhiên thuần túy. Nó chứa một phần thời gian tạo được mã hóa theo giây, nhưng **không phải nguồn audit time đáng tin cậy tuyệt đối**:

- Đồng hồ của client tạo ID có thể sai.
- Ứng dụng có thể tự cung cấp ObjectId cũ.
- ID có thể được tạo trước khi document được insert.
- Nó không lưu milliseconds hay timezone.
- Thứ tự ObjectId không luôn phản ánh thứ tự commit/transaction toàn cluster.

Nếu cần thời gian nghiệp vụ, hãy lưu trường `createdAt` riêng.

## 6. Ghi và đọc `ObjectId` bằng `Document`

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.ObjectId;

ObjectId orderId = new ObjectId();

Document newOrder = new Document("_id", orderId)
    .append("orderNo", "ORD-1001")
    .append("status", "NEW");

collection.insertOne(newOrder);

Document found = collection.find(
    new Document("_id", orderId)
).first();

if (found != null) {
    ObjectId storedId = found.getObjectId("_id");
    System.out.println(storedId.toHexString());
}
```

Đây là cách nhất quán khi `_id` thật sự có BSON type ObjectId.

### Đọc nhầm thành string

Không nên:

```java
// Không đúng nếu _id được giải mã thành ObjectId:
String id = found.getString("_id");
```

`getString()` mong đợi giá trị tương thích `String`. Với ObjectId, hãy dùng `getObjectId()` hoặc lấy object và kiểm tra type.

### Tìm theo ID từ REST path

HTTP path có thể đưa vào một chuỗi:

```text
GET /orders/65f000000000000000000101
```

Ứng dụng phải chuyển **có kiểm tra**:

```java
import org.bson.types.ObjectId;

public static ObjectId parseObjectId(String text) {
    if (text == null || !ObjectId.isValid(text)) {
        throw new IllegalArgumentException("ObjectId không hợp lệ");
    }
    return new ObjectId(text);
}
```

`ObjectId.isValid()` chỉ kiểm tra định dạng có thể tạo ObjectId, **không chứng minh document tồn tại hoặc user được phép xem nó**. AuthN/AuthZ và kiểm tra tenant/owner vẫn cần.

## 7. `_id` không bắt buộc là ObjectId

MongoDB cho phép `_id` sử dụng các BSON types được hỗ trợ theo những quy tắc của server, không bắt buộc toàn bộ collections phải dùng ObjectId. Một ứng dụng có thể sử dụng:

```javascript
{ _id: ObjectId("65f000000000000000000101"), name: "A" }
{ _id: "ORD-1001", name: "B" }
{ _id: NumberLong("1001"), name: "C" }
```

Một số ứng dụng chọn UUID làm khóa định danh. **Điều quan trọng là schema phải thống nhất**, vì:

```javascript
db.orders.find({ _id: "65f000000000000000000101" })
```

không match `_id` ObjectId có cùng chữ hex.

### Đừng đổi kiểu ID một cách tùy tiện

Nếu ứng dụng đang có:

```text
orders._id: ObjectId
payments.orderId: ObjectId
```

mà code mới chuyển `payments.orderId` thành string, lookup/index và các aggregation equality joins có thể không còn khớp.

Một migration ID cần xử lý **tất cả references**, indexes, URLs/API contract, historical records và rollback. Không thực hiện bằng cách đơn giản gọi `toString()` ở một service.

## 8. ObjectId và POJO mapping

Trong POJO, thuộc tính được đánh dấu `@BsonId` có thể ánh xạ tới `_id`.

```java
import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.types.ObjectId;

public class SimpleOrder {
    @BsonId
    private ObjectId id;
    private String orderNo;

    public SimpleOrder() {}

    public ObjectId getId() { return id; }
    public void setId(ObjectId id) { this.id = id; }

    public String getOrderNo() { return orderNo; }
    public void setOrderNo(String orderNo) {
        this.orderNo = orderNo;
    }
}
```

Khi POJO codec được cấu hình phù hợp, `id` ↔ `_id` là một mapping rõ ràng. Quy tắc sinh `_id` khi field null có thể liên quan đến id generator/conventions của POJO codec. Đừng mặc định mọi custom POJO class sẽ luôn được sinh ID đúng nếu không có codec hoặc conventions hợp lệ.

### Ý nghĩa trong REST/JSON

API có thể xuất `ObjectId` ra **hex string** cho frontend:

```json
{
  "id": "65f000000000000000000101",
  "orderNo": "ORD-1001"
}
```

Đây là **API representation**, không nhất thiết trùng BSON type. Khi nhận ID từ client, API phải parse lại thành ObjectId trước khi truy vấn collection đang dùng BSON ObjectId.

## 9. UUID là gì, và vì sao Java ↔ BSON dễ gặp lỗi?

`java.util.UUID` đại diện cho UUID 128-bit. Nhưng BSON không có một top-level BSON type tên UUID theo cách ObjectId là BSON type riêng. UUID được lưu dưới dạng **BSON Binary**, với subtype và cách sắp byte tương ứng.

Hai họ representation cần phân biệt:

- **UUID STANDARD:** BSON Binary **subtype 4**, byte order chuẩn cho UUID.
- **UUID LEGACY:** BSON Binary **subtype 3**, có những quy tắc byte order lịch sử khác nhau giữa drivers/platforms.

Ví dụ Java:

```java
import java.util.UUID;

UUID requestId = UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"
);
```

`UUID.toString()` cho ra chuỗi 36 ký tự dạng `8-4-4-4-12`. Nhưng nếu bạn `append("requestId", requestId)` và driver mã hóa bằng `STANDARD`, field lưu trên MongoDB là **Binary subtype 4**, không phải string 36 ký tự.

### Hai giá trị hiển thị giống UUID chưa chắc truy vấn khớp

```javascript
{
  requestId: "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"
}
```

là string.

Trong khi:

```javascript
{
  requestId: UUID("b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a")
}
```

được biểu diễn trong `mongosh` như UUID binary chuẩn. Equality giữa BSON String và BSON Binary **không tự chuyển kiểu**.

## 10. Cấu hình `UuidRepresentation.STANDARD` rõ ràng

Khi dùng UUID, nên đặt quy tắc representation **có chủ đích** và thống nhất giữa mọi ứng dụng.

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.UuidRepresentation;

String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Thiếu MONGODB_URI");
}

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoCollection<Document> requests = client
        .getDatabase("java_bson_mapping_lab")
        .getCollection("requests");

    // Chỉ minh họa cấu hình client ở scope này.
}
```

Khi dùng `UuidRepresentation.STANDARD`, driver có đủ quy tắc encode `java.util.UUID` thành BSON Binary subtype 4 và giải mã UUID theo chế độ tương ứng qua codec thích hợp.

### Vì sao phải explicit?

Ở những phiên bản Java driver hiện đại, `UNSPECIFIED` có thể là mặc định để tránh vô tình ghi UUID bằng representation không rõ. Khi encode UUID mà chưa cấu hình representation hợp lệ, bạn có thể gặp `CodecConfigurationException` hoặc thông báo tương đương. Đây là cơ chế phòng tránh dữ liệu UUID bị ghi theo byte order sai.

**Không sửa bằng cách chọn `JAVA_LEGACY` tùy tiện** nếu mục tiêu là dữ liệu mới. STANDARD là lựa chọn thông dụng cho thiết kế mới cần tương tác đa ngôn ngữ; chỉ dùng LEGACY khi thật sự đang đọc/ghi dữ liệu lịch sử có contract như vậy.

## 11. Ghi UUID bằng `Document` và truy vấn đúng type

Ví dụ dùng biến `requests` từ client đã cấu hình STANDARD:

```java
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.UUID;

UUID requestId = UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"
);

requests.insertOne(new Document("requestId", requestId)
    .append("state", "PENDING"));

Document found = requests.find(
    Filters.eq("requestId", requestId)
).first();
```

Filter truyền trực tiếp `UUID` cho codec encode khi gửi tới server. **Không thay `requestId` bằng `requestId.toString()`** nếu field được lưu BSON Binary UUID: string sẽ không match binary.

### Kiểm tra subtype và byte order bằng `BsonDocument`

```java
import org.bson.BsonBinary;
import org.bson.BsonDocument;
import org.bson.UuidRepresentation;

BsonDocument bson = requests
    .withDocumentClass(BsonDocument.class)
    .find(Filters.eq("requestId", requestId))
    .first();

if (bson != null) {
    BsonBinary raw = bson.getBinary("requestId");
    UUID parsed = raw.asUuid(UuidRepresentation.STANDARD);
    System.out.println(parsed);
}
```

`BsonDocument` cho phép đọc field ở mức BSON types, rất hữu ích khi cần điều tra subtype. Nếu subtype hoặc representation không phù hợp, conversion có thể báo lỗi hoặc tạo UUID khác kỳ vọng.

### Chú ý khi dùng `Document#get()`

Giá trị decoded từ BSON Binary trong `Document` có thể phụ thuộc codec/registry; không nên ép kiểu `(UUID) document.get("requestId")` mà chưa biết behavior của codec đó. Khi cần kiểm tra chắc subtype, dùng `BsonDocument`. Khi dùng POJO typed property `UUID`, cần registry/UuidRepresentation nhất quán.

## 12. UUID subtype 3/4 và migration dữ liệu cũ

BSON Binary **subtype 3** là một kiểu lưu UUID lịch sử. Các legacy representations gồm những biến thể thường được gọi:

- `JAVA_LEGACY`.
- `C_SHARP_LEGACY`.
- `PYTHON_LEGACY`.

Chúng có thể khác nhau về cách biểu diễn byte/ordering. **Không thể chỉ nhìn một chuỗi UUID hiển thị rồi khẳng định dữ liệu subtype 3 được ghi bằng representation nào.**

Một hệ thống có thể gặp:

```text
Ứng dụng Java cũ
    UUID -> subtype 3 JAVA_LEGACY

Ứng dụng Java mới
    UUID -> subtype 4 STANDARD
```

Nếu cùng một logical UUID có hai binary representations, equality/index matching có thể coi chúng là **hai giá trị khác nhau**. Unique index cũng chỉ áp ràng buộc lên BSON values thực, không tự normalize legacy và standard UUID.

### Migration UUID an toàn

1. **Khảo sát:** tìm các fields UUID, indexes, binary subtypes và writers.
2. **Xác định nguồn:** biết ứng dụng/driver phiên bản nào đã tạo subtype 3.
3. **Chốt canonical format:** thường là STANDARD subtype 4 cho dữ liệu mới.
4. **Viết conversion có nhận thức representation:** không copy 16 bytes cũ sang subtype 4 rồi giả định cùng UUID.
5. **Migration references:** nếu UUID đóng vai khóa liên kết giữa collections, đổi đồng bộ mọi references.
6. **Chạy thử với fixtures:** chọn những UUID đã biết chính xác từ ứng dụng legacy, so sánh trước/sau.
7. **Lập kế hoạch dual-read/dual-write hoặc cutover:** theo contract của hệ thống.
8. **Kiểm tra indexes và uniqueness:** tránh trùng logical IDs khác binary representations.
9. **Dùng backup và rollback:** không sửa trực tiếp binary fields trong production mà chưa kiểm chứng.

### Khi nào lưu UUID dạng string?

Lưu string đơn giản hóa một số API và công cụ, nhưng cần:

- Chấp nhận chi phí dung lượng/index khác với Binary.
- Định nghĩa lowercase/canonical dashed form.
- Không trộn string và binary trong cùng field.
- Không quên rằng equality có thể phân biệt chữ hoa/chữ thường/collation.

Không có quy tắc mọi UUID phải luôn là Binary. **Quan trọng hơn là schema ổn định và nhất quán giữa writers/readers.**

## 13. ObjectId khác UUID như thế nào?

| Thuộc tính | ObjectId | UUID |
| --- | --- | --- |
| BSON representation | Type ObjectId riêng | Binary subtype 4/legacy subtype 3 hoặc String theo schema |
| Java type | `ObjectId` | `UUID` |
| Kích thước binary cơ bản | 12 byte | 16 byte |
| Hiển thị phổ biến | 24 hex | 36 ký tự dashed |
| Có thành phần timestamp? | Có timestamp theo giây trong cấu trúc | UUID thông thường không nên coi là creation timestamp |
| Driver encode | ObjectId codec | UUID codec và representation |
| Có thể dùng làm `_id`? | Có | Có với thiết kế/schema phù hợp |
| Lưu ý migration | String hex không tự thành ObjectId | subtype 3/4, byte ordering và String/Binary |

ObjectId không phải “UUID viết ngắn”, và UUID không phải ObjectId. Không cast trực tiếp giữa hai classes. Nếu hệ thống dùng UUID làm `_id`, cần chọn BSON binary representation hoặc string và đảm bảo tất cả truy vấn/index/DBRefs liên quan thống nhất.

## 14. Decimal128: tại sao dùng cho tiền tệ?

Kiểu `double` biểu diễn số theo IEEE 754 binary floating-point. Nhiều phân số thập phân đơn giản như `0.1` không thể biểu diễn chính xác bằng nhị phân hữu hạn. Điều này có thể tạo sai số khi cộng/trừ/nhân số tiền.

Java cung cấp `java.math.BigDecimal` cho tính toán thập phân; MongoDB cung cấp BSON **Decimal128** để lưu các giá trị thập phân với độ chính xác cao.

Ví dụ:

```javascript
{
  sku: "SKU-A",
  unitPrice: NumberDecimal("199.90"),
  taxRate: NumberDecimal("0.08")
}
```

Đây là Decimal128, không phải Double.

### Đặc tính quan trọng

- Decimal128 có **tối đa 34 chữ số thập phân có nghĩa** và phạm vi exponent theo chuẩn decimal128.
- Không phải mọi giá trị `BigDecimal` tùy ý có thể được biểu diễn chính xác trong Decimal128.
- Nó hỗ trợ những giá trị đặc biệt như NaN, Infinity theo chuẩn decimal128; domain tiền tệ thường **không nên chấp nhận** các giá trị đó.
- Khi tính toán tiền, nên định nghĩa rõ **scale, rounding mode, currency và invariant**.
- Decimal128 lưu được chính xác nhiều giá trị thập phân thực tế, nhưng không thay business rounding policy.

Nếu cần tính tiền theo đơn vị đồng/cent nguyên và biết rõ range, dùng `Long` số đơn vị nhỏ nhất cũng có thể là một lựa chọn phù hợp. Không có quy tắc mọi giá tiền phải Decimal128.

## 15. Đừng tạo BigDecimal từ `double`

Ví dụ Java:

```java
import java.math.BigDecimal;

BigDecimal wrong = new BigDecimal(0.1);
BigDecimal right = new BigDecimal("0.1");
BigDecimal alsoRight = BigDecimal.valueOf(0.1);

System.out.println(wrong);
System.out.println(right);
```

`new BigDecimal(0.1)` nhận **giá trị nhị phân đã xấp xỉ** của `double`, nên có thể sinh một dãy chữ số dài không mong muốn. `new BigDecimal("0.1")` biểu diễn chính xác chuỗi thập phân.

Khi nguồn dữ liệu là request JSON, CSV hoặc hệ thống khác, nên parse tiền từ **chuỗi decimal** hoặc cơ chế decimal-aware của parser, không đưa qua `double` trung gian mà không có lý do.

## 16. Ghi Decimal128 vào MongoDB bằng `Document`

```java
import java.math.BigDecimal;
import org.bson.Document;
import org.bson.types.Decimal128;

BigDecimal amount = new BigDecimal("199.90");
Decimal128 bsonAmount = new Decimal128(amount);

Document product = new Document("sku", "SKU-A")
    .append("unitPrice", bsonAmount)
    .append("currency", "VND");

products.insertOne(product);
```

Ở đây `products` là `MongoCollection<Document>` từ một database lab.

### Đọc lại

```java
Document found = products.find(
    new Document("sku", "SKU-A")
).first();

if (found != null) {
    Decimal128 value = found.get("unitPrice", Decimal128.class);
    BigDecimal money = value.bigDecimalValue();
    System.out.println(money.toPlainString());
}
```

Chỉ gọi `bigDecimalValue()` khi giá trị Decimal128 là một số hữu hạn có thể chuyển đổi phù hợp. Với `NaN` hoặc ±Infinity, phải xử lý chính sách riêng; không giả định mọi Decimal128 đều là một `BigDecimal` hợp lệ của domain.

### Chuỗi thập phân và precision

```java
Decimal128 price = Decimal128.parse("199.90");
BigDecimal exact = price.bigDecimalValue();
```

Không gọi `value.doubleValue()` để chuyển về `double` rồi lại tạo `BigDecimal`, vì con đường đó có thể đánh mất độ chính xác.

### BigDecimal vượt khả năng biểu diễn

```java
BigDecimal veryPrecise = new BigDecimal(
    "0.123456789012345678901234567890123456789");

// Decimal128 chỉ hỗ trợ giới hạn precision/exponent nhất định.
// Việc encode chính xác giá trị này có thể không thực hiện được.
```

Không mặc định driver sẽ tự làm tròn theo business policy. Hãy xác thực precision/range và **tự quyết định rounding** trước khi lưu nếu domain chấp nhận.

## 17. `BigDecimal` trong POJO có luôn thành Decimal128 không?

Với codec registry phù hợp của Java BSON driver, `BigDecimal` có thể được mã hóa thành BSON Decimal128. Tuy nhiên, việc ánh xạ POJO phụ thuộc vào:

- Codec registry đang dùng.
- Java driver/framework version.
- `PojoCodecProvider` và registration.
- Custom codecs/conventions.
- Chính sách precision/rounding của ứng dụng.

Một POJO:

```java
public class Product {
    private String sku;
    private BigDecimal unitPrice;

    public Product() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public BigDecimal getUnitPrice() { return unitPrice; }
    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }
}
```

Nếu POJO codec và BigDecimal codec đã được đăng ký đúng, `unitPrice` có thể đi thành BSON Decimal128. **Phải test kiểu BSON thực tế** thay vì chỉ nhìn JSON trong response. Trong các đường ghi với `Document` cần hành vi rõ ràng, `new Decimal128(bigDecimal)` giúp loại bỏ sự mơ hồ.

## 18. Decimal128 với truy vấn, tính toán và index

```javascript
db.products.createIndex({ unitPrice: 1 });

db.products.find({
  unitPrice: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("500.00")
  }
});
```

Trong Java:

```java
import com.mongodb.client.model.Filters;
import java.math.BigDecimal;
import org.bson.types.Decimal128;

products.find(
    Filters.and(
        Filters.gte("unitPrice",
            new Decimal128(new BigDecimal("100.00"))),
        Filters.lt("unitPrice",
            new Decimal128(new BigDecimal("500.00")))
    )
);
```

MongoDB có quy tắc so sánh chung cho numeric BSON types, nhưng kết hợp Double, Decimal128, Int32/Int64 có thể gây khó kiểm soát **precision, aggregation result type và business behavior**. Đối với tiền, nên chuẩn hóa một schema/type và thống nhất operands trong queries/updates.

### `$inc` và phép cộng

```java
import com.mongodb.client.model.Updates;

products.updateOne(
    Filters.eq("sku", "SKU-A"),
    Updates.inc("unitPrice",
        new Decimal128(new BigDecimal("0.10")))
);
```

Đoạn code minh họa cách sử dụng Decimal128 operand; trong ứng dụng thực, **cập nhật giá tiền** thường còn cần audit, version/concurrency control và quy tắc làm tròn. Không nên dùng `double` cho một nửa dữ liệu, Decimal128 cho nửa còn lại mà không có kế hoạch chuẩn hóa.

## 19. Scale và so sánh `BigDecimal`

`BigDecimal` có thể phân biệt scale khi dùng `equals()`:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
```

Trong business rule, nếu cần so **giá trị số**, dùng `compareTo()` theo domain; nếu scale có ý nghĩa (ví dụ độ chính xác theo đơn vị đo), lưu/kiểm tra scale riêng.

### Quy tắc rounding

```java
import java.math.RoundingMode;

BigDecimal subtotal = new BigDecimal("19.995");
BigDecimal rounded =
    subtotal.setScale(2, RoundingMode.HALF_UP);
```

Chọn `HALF_UP` ở đây **chỉ là ví dụ**, không mặc định đúng với thuế, ngân hàng hoặc mọi tiền tệ. Một số nghiệp vụ dùng `HALF_EVEN` hoặc quy định riêng. Cần bảo đảm chính sách rounding được áp dụng nhất quán **trước khi lưu Decimal128** và trong tính toán phía Java.

## 20. Ngày giờ: MongoDB Date thực sự lưu gì?

BSON **DateTime** lưu một giá trị **signed 64-bit integer tính bằng milliseconds từ Unix epoch (UTC)**.

```text
Java Instant: 2026-11-14T08:15:30.123Z
        |
        v
epoch milliseconds (long)
        |
        v
BSON DateTime
        |
        v
mongosh: ISODate("2026-11-14T08:15:30.123Z")
```

Kiểu Date **không lưu tên timezone** như `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin` và không lưu offset gốc `+07:00`. Hai chuỗi thời gian khác múi giờ có thể đại diện **cùng một instant**, và khi lưu BSON Date sẽ có **cùng giá trị milliseconds**.

### Ví dụ cùng thời điểm

```text
UTC:     2026-11-14 08:00:00 Z
UTC+07:  2026-11-14 15:00:00 +07:00

Hai cách biểu diễn một instant.
```

Không suy từ việc `mongosh` hiển thị `Z` rằng ứng dụng đã “đổi sai múi giờ”. Có thể chỉ là **hiển thị cùng thời điểm trong UTC**.

## 21. `java.util.Date` và `Instant`

`java.util.Date` là kiểu lịch sử biểu diễn thời điểm theo milliseconds; `java.time.Instant` trong Java Time API phù hợp để biểu diễn một instant trên timeline UTC và có thể có precision cao hơn milliseconds.

Ví dụ convert:

```java
import java.time.Instant;
import java.util.Date;

Instant time = Instant.parse("2026-11-14T08:15:30.123Z");

Date legacyDate = Date.from(time);
Instant restored = legacyDate.toInstant();

System.out.println(restored);
```

Java `Date` không tự mang timezone. Việc format bằng `Date.toString()` có thể sử dụng timezone mặc định của JVM để **hiển thị**, nhưng giá trị thời điểm vẫn giống nhau.

### Ghi Date trong Document

```java
import java.time.Instant;
import java.util.Date;
import org.bson.Document;

Instant createdAt =
    Instant.parse("2026-11-14T08:15:30.123Z");

events.insertOne(
    new Document("eventType", "LOGIN")
        .append("createdAt", Date.from(createdAt))
);
```

`Date.from(instant)` là một con đường rõ ràng, phù hợp khi dùng `Document` và muốn field có BSON DateTime.

### Đọc lại thành Instant

```java
Document event = events.find(
    new Document("eventType", "LOGIN")
).first();

if (event != null) {
    Date date = event.getDate("createdAt");
    Instant instant =
        date == null ? null : date.toInstant();
}
```

Không gọi `getString("createdAt")` nếu field được lưu BSON DateTime.

## 22. Precision: BSON Date chỉ lưu milliseconds

`Instant` trong Java có thể chứa nanoseconds:

```java
Instant precise =
    Instant.parse("2026-11-14T08:15:30.123456789Z");

Date encodedDate = Date.from(precise);
Instant roundTripped = encodedDate.toInstant();

System.out.println(roundTripped);
// 2026-11-14T08:15:30.123Z
```

Phần microsecond/nanosecond vượt quá milliseconds **không được giữ** khi chuyển qua BSON DateTime/`Date` theo cách này.

### Vì sao ảnh hưởng nghiệp vụ?

- Hai events cách nhau 100 microseconds có thể có cùng BSON DateTime.
- Không nên dựa chỉ vào timestamp milliseconds để phân xử thứ tự tuyệt đối của các events xảy ra cực nhanh.
- Một hệ thống cần precision micro/nano có thể cần field bổ sung như `epochNanos` (theo schema/range thích hợp) hoặc một logical sequence/counter.
- Khi đo độ trễ dưới 1 ms, không lưu toàn bộ kết quả chỉ bằng BSON DateTime rồi kỳ vọng còn nanoseconds.

Nếu dùng thêm field precision cao, cần định nghĩa rõ đơn vị, overflow range và cách query/index. Không tự lưu epoch nanoseconds vào `int` 32-bit.

## 23. `LocalDate` không phải một instant

`java.time.LocalDate` có nghĩa **ngày lịch**, không có giờ và timezone:

```java
import java.time.LocalDate;

LocalDate birthday =
    LocalDate.of(1995, 7, 21);
```

Nhiệm vụ “ngày sinh 21/07/1995” không hỏi thời điểm chính xác tính bằng milliseconds UTC. Nếu ép nó thành midnight UTC, người dùng ở timezone âm có thể thấy ngày trước khi ứng dụng render theo local zone.

### Hai chiến lược schema thường gặp

**A. Lưu date-only thành string ISO rõ nghĩa**

```javascript
{
  birthday: "1995-07-21"
}
```

Ưu điểm: nghĩa ngày lịch rõ ràng, không bị timezone shifting nếu toàn bộ hệ thống giữ convention. Cần đảm bảo format chuẩn `YYYY-MM-DD` và validation vì nó là string, không phải BSON Date.

**B. Dùng codec/convention cho LocalDate**

Một số Java time codecs ánh xạ `LocalDate` sang BSON DateTime theo quy ước ngày bắt đầu ở UTC. Đây là **convention của codec**, không có nghĩa LocalDate đột nhiên chứa timezone. API/service khác phải biết cùng convention khi decode.

Nếu nghiệp vụ quan trọng theo ngày địa phương, cần mô tả schema rõ trong tài liệu/API, không chỉ tin tên Java class.

## 24. `LocalDateTime` không có timezone

`LocalDateTime` gồm ngày và giờ **trên đồng hồ địa phương**, nhưng thiếu timezone/offset. Chẳng hạn:

```java
import java.time.LocalDateTime;

LocalDateTime scheduled =
    LocalDateTime.of(2026, 11, 14, 9, 0);
```

Giá trị trên **chưa đủ** để biết 09:00 là instant UTC nào. Cần một `ZoneId` hoặc offset:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local =
    LocalDateTime.of(2026, 11, 14, 9, 0);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant instant =
    local.atZone(zone).toInstant();
// 2026-11-14T02:00:00Z
```

Ở đây ví dụ dùng Asia/Ho_Chi_Minh với offset +07:00 vào ngày đã chọn. Đây chỉ là **quy tắc chuyển local time sang instant**; không phải timezone nên tự áp dụng cho mọi người dùng.

### Nếu cần nhớ timezone gốc

```javascript
{
  scheduledAt: ISODate("2026-11-14T02:00:00Z"),
  timeZone: "Asia/Ho_Chi_Minh",
  localTimeText: "2026-11-14T09:00:00"
}
```

Việc lưu cả `scheduledAt` và `timeZone` có thể cần thiết khi ứng dụng lập lịch theo múi giờ người dùng, hiển thị lại thông tin và xử lý daylight saving transitions ở các quốc gia khác.

Không lưu chỉ `"2026-11-14T09:00:00"` rồi cho rằng mọi client trên thế giới sẽ hiểu cùng instant.

## 25. Java Time codecs và cách chọn loại dữ liệu

Tùy version của MongoDB Java BSON Driver và codec registry, các codecs cho `Instant`, `LocalDate` và `LocalDateTime` có thể được cung cấp/đăng ký sẵn hoặc cần cấu hình bổ sung.

**Đừng dựa vào một assumption “mọi java.time class đều tự lưu”**. Một số kiểu như `OffsetDateTime` hoặc `ZonedDateTime` có thể không có codec trực tiếp trong registry đang dùng hoặc có semantics cần quy ước riêng.

### Quy tắc thực hành

| Nghiệp vụ | Java type | BSON schema dễ hiểu |
| --- | --- | --- |
| Thời điểm tạo bản ghi | `Instant` | DateTime |
| Thời điểm event | `Instant` | DateTime |
| Ngày sinh chỉ có ngày | `LocalDate` | ISO date string hoặc convention riêng |
| Giờ họp theo múi giờ | `ZonedDateTime`/`LocalDateTime + ZoneId` | DateTime instant + zone ID |
| Thời lượng | `Duration` | Long milliseconds/microseconds hoặc schema riêng |
| Số timestamp từ hệ cũ | `Long` | Định nghĩa rõ epoch units và convert |

### Tránh nhầm giây và milliseconds

`Instant.ofEpochSecond(...)` nhận giây; `Instant.ofEpochMilli(...)` nhận milliseconds. Nếu lấy `Date.getTime()` (milliseconds) rồi gọi `ofEpochSecond()`, thời điểm sẽ sai nghiêm trọng.

```java
long epochMillis = 1794644130123L; // giá trị ví dụ

Instant correct =
    Instant.ofEpochMilli(epochMillis);

// Sai khi epochMillis lại được hiểu là giây:
// Instant.ofEpochSecond(epochMillis);
```

Khi nhận timestamp qua Kafka/REST/CSV, ghi rõ `epochSeconds`, `epochMillis` hoặc `epochMicros` trong field/API contract.

## 26. Query ngày giờ: range với BSON DateTime

Khi field `createdAt` có BSON DateTime:

```javascript
db.events.createIndex({ createdAt: 1 });

db.events.find({
  createdAt: {
    $gte: ISODate("2026-11-14T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
});
```

Trong Java:

```java
import com.mongodb.client.model.Filters;
import java.time.Instant;
import java.util.Date;

Instant from = Instant.parse("2026-11-14T00:00:00Z");
Instant to = Instant.parse("2026-11-15T00:00:00Z");

events.find(Filters.and(
    Filters.gte("createdAt", Date.from(from)),
    Filters.lt("createdAt", Date.from(to))
));
```

**Khoảng nửa mở `[from, to)`** thường dễ dùng để query theo ngày và tránh xử lý “23:59:59.999...” với nhiều precision levels.

### Query ngày theo timezone người dùng

Nếu cần tìm các events xảy ra trong **ngày 14/11 theo Asia/Ho_Chi_Minh**:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;
import java.util.Date;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 14);

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

events.find(Filters.and(
    Filters.gte("createdAt", Date.from(start)),
    Filters.lt("createdAt", Date.from(end))
));
```

Lợi ích: MongoDB so sánh **instants UTC**, nhưng ranh giới ngày được tính đúng theo timezone nghiệp vụ. Ở những timezone có daylight saving, một ngày lịch có thể không dài đúng 24 giờ, nên không nên luôn lấy start rồi cộng cố định 86.400 giây để tìm ngày tiếp theo.

## 27. Java null không đồng nghĩa BSON null

Trong Java:

```java
String note = null;
```

đó là một object reference không trỏ tới giá trị. Khi viết MongoDB, có ít nhất **hai cách**:

**Field hiện diện và có BSON null:**

```java
Document a = new Document("name", "A")
    .append("note", null);
```

**Field không tồn tại:**

```java
Document b = new Document("name", "B");
```

Cả hai trường hợp có thể cho:

```java
System.out.println(a.get("note")); // null
System.out.println(b.get("note")); // null
```

Nhưng:

```java
System.out.println(a.containsKey("note")); // true
System.out.println(b.containsKey("note")); // false
```

**Đây là khác biệt rất quan trọng khi viết API, migration và validator.**

### BSON null ở mức `BsonDocument`

```java
import org.bson.BsonDocument;
import org.bson.BsonNull;
import org.bson.BsonString;

BsonDocument explicitNull = new BsonDocument()
    .append("name", new BsonString("A"))
    .append("note", BsonNull.VALUE);

BsonDocument absent = new BsonDocument()
    .append("name", new BsonString("B"));
```

`BsonNull.VALUE` biểu diễn rõ BSON Null. Nếu không append key, field không tồn tại.

## 28. MongoDB query với `null`

Giả sử collection `users` chứa:

```javascript
{ _id: 1, nickname: null }
{ _id: 2 }
{ _id: 3, nickname: "An" }
{ _id: 4, nickname: "" }
```

Truy vấn:

```javascript
db.users.find({ nickname: null });
```

trả về những document **field bằng BSON null hoặc field thiếu** theo equality null semantics của MongoDB; trong ví dụ, `_id: 1` và `_id: 2`.

Trong Java:

```java
import com.mongodb.client.model.Filters;

users.find(Filters.eq("nickname", null));
```

**Không dùng filter này khi business requirement là “chỉ những document có field và giá trị null”**.

### Chỉ BSON null, không gồm missing

```javascript
db.users.find({
  nickname: { $type: 10 }
});
```

Type number 10 là BSON Null.

Trong Java:

```java
import org.bson.BsonType;
import com.mongodb.client.model.Filters;

users.find(Filters.type("nickname", BsonType.NULL));
```

Nếu API/version bạn sử dụng có overload khác, có thể tạo filter BSON trực tiếp:

```java
users.find(new Document("nickname",
    new Document("$type", 10)));
```

### Chỉ field tồn tại, bất kể giá trị

```javascript
db.users.find({
  nickname: { $exists: true }
});
```

Bao gồm field có giá trị `null`, `""` hoặc string bình thường.

### Chỉ field không tồn tại

```javascript
db.users.find({
  nickname: { $exists: false }
});
```

Trong Java:

```java
users.find(Filters.exists("nickname", false));
```

### Field tồn tại và không null

```javascript
db.users.find({
  nickname: { $ne: null }
});
```

Với MongoDB semantics, điều này chọn field có giá trị khác null theo tình huống phù hợp; vẫn cần nghĩ đến **chuỗi rỗng** `""`, số `0` và boolean `false` là những giá trị khác null.

## 29. `null`, missing, chuỗi rỗng và giá trị mặc định

| BSON state | Nghĩa có thể có | Java khi đọc qua Document |
| --- | --- | --- |
| Field missing | Chưa cung cấp/không áp dụng | `get(key)==null`, `containsKey==false` |
| Field = BSON null | Có field nhưng chưa có giá trị | `get(key)==null`, `containsKey==true` |
| Field = `""` | Người dùng gửi chuỗi rỗng | `String` rỗng |
| Field = `0` | Giá trị số bằng 0 | `Integer/Long/Decimal128/...` theo BSON |
| Field = `false` | Giá trị boolean false | `Boolean.FALSE` |
| Field = `[]` | Mảng rỗng | `List` rỗng hoặc giá trị tương ứng |

Trong một domain:

- `middleName: null` có thể nghĩa “đã hỏi nhưng không biết”.
- Không có field `middleName` có thể nghĩa “schema cũ chưa thu thập”.
- `middleName: ""` có thể nghĩa “người dùng xóa nội dung”.

Đừng tự gộp ba trạng thái nếu nghiệp vụ cần phân biệt. Tương tự, dùng số 0 làm giá trị mặc định cho một trường đo đạc **không giống** một measurement bị thiếu.

## 30. `Updates.set(field, null)` khác `Updates.unset(field)`

Trong Java Sync Driver:

```java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

// Field tồn tại, giá trị BSON Null:
users.updateOne(
    Filters.eq("_id", 1),
    Updates.set("nickname", null)
);

// Loại bỏ field khỏi document:
users.updateOne(
    Filters.eq("_id", 1),
    Updates.unset("nickname")
);
```

Đây là hai hành vi khác nhau. Nếu ứng dụng dùng REST PATCH, cần định nghĩa:

- Request thiếu field -> giữ nguyên giá trị hay xóa field?
- Request có `"nickname": null` -> set BSON null hay unset?
- Request có `"nickname": ""` -> chuỗi rỗng có hợp lệ không?

**Không đồng nhất Java null thành `$unset` một cách ngầm định** nếu API contract chưa quy định rõ.

## 31. Null trong POJO và primitive/wrapper types

Một POJO:

```java
public class UserProfile {
    private String nickname;
    private Integer age;
    private int loginCount;

    public UserProfile() {}

    public String getNickname() { return nickname; }
    public void setNickname(String nickname) {
        this.nickname = nickname;
    }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }

    public int getLoginCount() { return loginCount; }
    public void setLoginCount(int loginCount) {
        this.loginCount = loginCount;
    }
}
```

Nếu BSON field `age` thiếu hoặc là null, Java property `Integer` có thể là `null` sau decode. Nếu field `loginCount` thiếu, primitive `int` chỉ có thể mang giá trị mặc định `0`, nên ứng dụng **không thể chỉ từ POJO instance phân biệt “field chưa có” với “field có số 0”**.

### POJO serialization có thể bỏ qua null

Tùy conventions/annotations/codecs, một property Java `null` có thể bị bỏ qua khi serialize thay vì ghi BSON Null. Vì thế không nên khẳng định:

```text
Java null property -> BSON Null
```

luôn đúng cho mọi POJO codec.

Nếu schema yêu cầu field **hiện diện với BSON null**, nên kiểm tra behavior của codec/convention hoặc thao tác bằng `Document`/`BsonDocument` rõ ràng. Ngược lại, nếu muốn omit null fields, cần cấu hình conventions/annotations theo version và kiểm thử dữ liệu thực lưu.

## 32. Schema validation phân biệt null và missing

MongoDB `$jsonSchema` có:

- `required` kiểm tra field **phải tồn tại**.
- `bsonType` kiểm tra BSON type của field nếu nó hiện diện.

Ví dụ yêu cầu `nickname` tồn tại nhưng chấp nhận null:

```javascript
db.createCollection("user_profiles", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["userId", "nickname"],
      properties: {
        userId: { bsonType: "string" },
        nickname: {
          bsonType: ["string", "null"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Giả sử user profile:

```javascript
{ userId: "U1", nickname: null }
```

**Hợp lệ** theo hai điều kiện về nickname: field có mặt và type là null được cho phép.

```javascript
{ userId: "U2" }
```

**Không hợp lệ** vì thiếu field nickname trong `required`.

```javascript
{ userId: "U3", nickname: 123 }
```

**Không hợp lệ** vì nickname là numeric, không thuộc types được phép.

### Nếu field optional nhưng không cho null

Bỏ `nickname` khỏi `required`, chỉ cho `bsonType: "string"`. Khi đó:

- Missing field: hợp lệ.
- String value: hợp lệ.
- BSON Null: không hợp lệ nếu field hiện diện.

Đây là cách biểu diễn một chính sách khác hoàn toàn.

## 33. `$ifNull` coi missing và null tương tự

Trong aggregation:

```javascript
db.users.aggregate([
  {
    $project: {
      nicknameSafe: {
        $ifNull: ["$nickname", "(chưa có)"]
      }
    }
  }
]);
```

`$ifNull` xử lý cả **null và missing/undefined theo semantics của operator**, rất phù hợp nếu UI muốn fallback giống nhau. Nhưng nếu mục tiêu là **thống kê riêng số missing và số BSON null**, cần dùng truy vấn/biểu thức phân biệt types thay vì gộp tất cả bằng `$ifNull`.

### Đừng dùng `$ifNull` để sửa mất dữ liệu theo mặc định

Giá trị fallback trong aggregation là **kết quả tính toán**, không tự sửa document được lưu trữ. Nếu muốn backfill field thiếu, cần một migration/update riêng và phải phân biệt missing vs null theo business requirements.

## 34. Extended JSON: giữ thông tin BSON khi xuất/nhập

JSON chuẩn không có ObjectId, Decimal128 hay DateTime. **MongoDB Extended JSON** có thể biểu diễn những types này để trao đổi:

```json
{
  "_id": {
    "$oid": "65f000000000000000000101"
  },
  "requestId": {
    "$binary": {
      "base64": "t/MEcn+9SqGbiiXsvPUiSg==",
      "subType": "04"
    }
  },
  "amount": {
    "$numberDecimal": "199.90"
  },
  "createdAt": {
    "$date": "2026-11-14T08:15:30.123Z"
  },
  "cancelledAt": null
}
```

**Lưu ý:** ví dụ `$binary` minh họa syntax Extended JSON và subtype; base64 trong payload phải được tạo/kiểm tra từ bytes thật khi dùng ngoài bài học. Không dùng chuỗi base64 minh họa làm fixture duy nhất để chứng minh một UUID cụ thể nếu chưa kiểm tra encoding.

### Khác biệt giữa canonical và relaxed forms

MongoDB Extended JSON có những forms để biểu diễn BSON types chính xác hoặc dễ đọc. Ví dụ DateTime có thể được biểu diễn bằng `$date` string khi thích hợp; những giá trị có thể dùng `$numberLong` trong canonical representation.

Nếu API REST phát ra:

```json
{
  "amount": 199.9,
  "createdAt": "2026-11-14T08:15:30.123Z"
}
```

client có thể parse `amount` thành JavaScript Number (binary double) và `createdAt` thành string. Đây **không còn là cùng một ánh xạ BSON type end-to-end**. API có thể chủ đích dùng representation dễ tiêu thụ, nhưng cần quy định cách parse/validate khi lưu lại.

## 35. Dùng `BsonDocument` để xác nhận kiểu dữ liệu thực tế

Khi nghi ngờ một field:

```java
import org.bson.BsonDocument;
import org.bson.BsonType;

BsonDocument raw = products
    .withDocumentClass(BsonDocument.class)
    .find(new Document("sku", "SKU-A"))
    .first();

if (raw != null) {
    BsonType type = raw.get("unitPrice").getBsonType();
    System.out.println(type);
}
```

Nếu `unitPrice` có BSON Decimal128, type sẽ là `DECIMAL128`; nếu dữ liệu được ghi nhầm bằng Double, bạn sẽ thấy `DOUBLE`. Cẩn thận với field missing: `raw.get("unitPrice")` có thể trả `null`, nên ở production cần kiểm tra `containsKey` trước khi gọi `getBsonType()`.

### Kiểm tra trong `mongosh` bằng `$type`

```javascript
db.products.aggregate([
  {
    $project: {
      sku: 1,
      storedType: { $type: "$unitPrice" }
    }
  },
  { $limit: 20 }
]);
```

Ví dụ có thể trả:

```text
{ sku: "SKU-A", storedType: "decimal" }
{ sku: "SKU-B", storedType: "double" }
{ sku: "SKU-C", storedType: "missing" }
```

Đây là cách phát hiện data drift ở cấp BSON type trước khi quyết định migration.

## 36. POJO codec registry hoàn chỉnh

Java Sync Driver có thể sử dụng `PojoCodecProvider` để ánh xạ class Java sang BSON documents.

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.UuidRepresentation;
import org.bson.codecs.configuration.CodecRegistry;
import org.bson.codecs.pojo.PojoCodecProvider;

import static org.bson.codecs.configuration.CodecRegistries
    .fromProviders;
import static org.bson.codecs.configuration.CodecRegistries
    .fromRegistries;

String uri = System.getenv("MONGODB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Thiếu MONGODB_URI");
}

CodecRegistry pojoRegistry = fromRegistries(
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(
        PojoCodecProvider.builder()
            .automatic(true)
            .build()
    )
);

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .codecRegistry(pojoRegistry)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase database = client
        .getDatabase("java_bson_mapping_lab");

    MongoCollection<PaymentRecord> payments =
        database.getCollection("payments", PaymentRecord.class);

    // Sử dụng payments trong phạm vi client còn mở.
}
```

Trong ví dụ trên:

- `MongoClientSettings.getDefaultCodecRegistry()` cung cấp những codecs mặc định của driver.
- `PojoCodecProvider.builder().automatic(true)` cho phép tự tạo POJO codec cho những classes phù hợp; production có thể muốn đăng ký classes/conventions tường minh hơn.
- `UuidRepresentation.STANDARD` quy định biểu diễn UUID mới.
- `getCollection("payments", PaymentRecord.class)` tạo typed collection.

### Tại sao không dùng automatic POJO codec cho mọi class tùy tiện?

Một class có fields/getters phức tạp, inheritance, immutable constructors hoặc custom types có thể cần codec/conventions/annotations cụ thể. Automatic mapping giảm boilerplate, nhưng không thay schema contract và tests kiểm tra BSON type.

## 37. POJO kết hợp ObjectId, UUID, BigDecimal, Date và nullable fields

Ví dụ một model có đủ các kiểu đang học:

```java
import java.math.BigDecimal;
import java.util.Date;
import java.util.UUID;
import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.types.ObjectId;

public class PaymentRecord {
    @BsonId
    private ObjectId id;
    private UUID requestId;
    private BigDecimal amount;
    private Date createdAt;
    private Date cancelledAt;
    private String note;

    public PaymentRecord() {}

    public ObjectId getId() { return id; }
    public void setId(ObjectId id) { this.id = id; }

    public UUID getRequestId() { return requestId; }
    public void setRequestId(UUID requestId) {
        this.requestId = requestId;
    }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public Date getCreatedAt() { return createdAt; }
    public void setCreatedAt(Date createdAt) {
        this.createdAt = createdAt;
    }

    public Date getCancelledAt() { return cancelledAt; }
    public void setCancelledAt(Date cancelledAt) {
        this.cancelledAt = cancelledAt;
    }

    public String getNote() { return note; }
    public void setNote(String note) { this.note = note; }
}
```

### Ghi POJO

```java
PaymentRecord payment = new PaymentRecord();
payment.setId(new ObjectId());
payment.setRequestId(UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"));
payment.setAmount(new BigDecimal("125000.50"));
payment.setCreatedAt(
    Date.from(Instant.parse("2026-11-14T08:15:30.123Z")));
payment.setCancelledAt(null);
payment.setNote("Thanh toán thử nghiệm");

payments.insertOne(payment);
```

Với codec registry phù hợp, mong đợi:

- `id` được ánh xạ thành BSON `_id` ObjectId.
- `requestId` thành UUID Binary STANDARD subtype 4.
- `amount` thành Decimal128 theo codec BigDecimal.
- `createdAt` thành BSON DateTime.
- `cancelledAt` và `note` chịu **null serialization policy** của POJO codec, có thể bị omit thay vì ghi explicit BSON Null.

**Không kết luận null fields đã được lưu như BSON Null nếu chưa đọc lại dữ liệu thực.** Nếu schema bắt buộc field phải hiện diện dù null, cần codec/convention hoặc cách ghi rõ ràng tương ứng.

### Không tự tạo lại `_id` trong retry

Nếu write timeout nhưng server đã insert thành công, retry với `new ObjectId()` khác sẽ tạo một document thứ hai. Khi cần idempotency, nên dùng request ID unique, giữ nguyên ID trên retry hoặc triển khai conditional upsert theo business key.

## 38. Kiểm thử round-trip trên dữ liệu lab

Một bài test thực hành nên kiểm tra **giá trị và BSON type**:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;

ObjectId id = new ObjectId();
UUID uuid = UUID.fromString(
    "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a");
Instant instant =
    Instant.parse("2026-11-14T08:15:30.123Z");
BigDecimal amount = new BigDecimal("100.25");

Document source = new Document("_id", id)
    .append("requestId", uuid)
    .append("amount", new Decimal128(amount))
    .append("createdAt", Date.from(instant))
    .append("cancelledAt", null);

testCollection.insertOne(source);

Document restored = testCollection.find(
    new Document("_id", id)).first();

if (restored == null) {
    throw new AssertionError("Không tìm thấy document");
}

if (!id.equals(restored.getObjectId("_id"))) {
    throw new AssertionError("ObjectId không khớp");
}

BigDecimal restoredAmount =
    restored.get("amount", Decimal128.class).bigDecimalValue();

if (restoredAmount.compareTo(amount) != 0) {
    throw new AssertionError("Decimal128 không khớp");
}

Instant restoredTime =
    restored.getDate("createdAt").toInstant();

if (!restoredTime.equals(instant)) {
    throw new AssertionError("DateTime không khớp");
}

if (!restored.containsKey("cancelledAt")) {
    throw new AssertionError("Mong đợi explicit BSON null");
}
```

Ví dụ giả định `testCollection` thuộc `MongoCollection<Document>` sử dụng client đã cấu hình UUID STANDARD. Test UUID nên đọc thêm `BsonDocument` để kiểm tra subtype/value, thay vì chỉ tin `Document#get()` luôn trả cùng class UUID.

### Kiểm thử timestamp sub-millisecond

Nếu test đầu vào `Instant` có nanoseconds không chia hết cho 1.000.000, không nên assert hai `Instant` hoàn toàn bằng nhau sau round-trip BSON DateTime. Nên định nghĩa **precision policy**: làm tròn/cắt về milliseconds, hoặc lưu thêm dữ liệu nếu cần độ chính xác cao hơn.

## 39. Migration khi collection có dữ liệu hỗn hợp type

Một collection có thể chứa các phiên bản khác nhau của schema:

```javascript
// Legacy:
{
  _id: "65f000000000000000000101",
  requestId: "b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a",
  amount: 199.9,
  createdAt: "2026-11-14T08:15:30.123Z",
  note: ""
}

// Mong muốn:
{
  _id: ObjectId("65f000000000000000000101"),
  requestId: UUID("b7f30472-7fbd-4aa1-9b8a-25ecbcf5224a"),
  amount: NumberDecimal("199.90"),
  createdAt: ISODate("2026-11-14T08:15:30.123Z"),
  note: null
}
```

**Đừng chạy một migration đổi tất cả chỉ vì cùng hình thức hiển thị.** Có những quyết định nghiệp vụ:

- `_id` String có thể đang được API và các foreign references sử dụng.
- `requestId` String/UUID Binary cần migration toàn bộ writers và indexes.
- `amount` Double có thể đã mất chính xác từ trước, không thể tái tạo số gốc chỉ bằng cast sang Decimal128.
- `createdAt` String có thể chứa timezone hoặc local time mơ hồ.
- `note: ""` có thể khác `note: null` theo API semantics.

### Các bước migration có kiểm soát

1. **Đếm type thực tế** bằng `$type`, tách theo source/version nếu có.
2. **Chọn schema đích** với mapping ObjectId/UUID/Decimal128/Date/null rõ ràng.
3. **Chọn conversion policy** cho precision, timezone, null/missing.
4. **Chạy trên bản sao/staging** và so sánh kết quả.
5. **Kiểm tra references** khi đổi ID hoặc khóa liên kết.
6. **Giữ raw value/audit** khi phép conversion có thể mất thông tin.
7. **Đảm bảo writers mới dùng cùng codec registry** trước/đồng thời migration.
8. **Kiểm tra uniqueness, indexes và validators** sau đổi type.
9. **Dùng batch/throttling/idempotency**, không khóa nghẽn hệ thống.
10. **Có backup/rollback**, xác nhận bằng query nghiệp vụ thay vì chỉ count.

Đặc biệt với Decimal128, việc ép `double` thành Decimal128 **không sửa được** sai số nhị phân đã ghi trước đó nếu không có nguồn tiền chính xác để đối chiếu.

## 40. Index và equality khi đổi BSON type

Index lưu những BSON values với loại dữ liệu cụ thể. Việc chuyển một field từ String sang ObjectId hoặc UUID binary có thể ảnh hưởng:

- Equality filters.
- Compound index selectivity.
- Unique constraints.
- Aggregation `$lookup` giữa collections.
- Range queries và sort.
- Dữ liệu historical còn dùng type cũ.

Ví dụ:

```javascript
db.payments.createIndex({ orderId: 1 });

// orderId ObjectId:
db.payments.find({
  orderId: ObjectId("65f000000000000000000101")
});

// orderId String, giá trị chữ giống nhau:
db.payments.find({
  orderId: "65f000000000000000000101"
});
```

Hai truy vấn không tương đương nếu dữ liệu mixed types.

### Chiến lược quá độ

Trong migration có thể tạm hỗ trợ đọc cả legacy và current forms, nhưng phải có:

- Thời điểm kết thúc compatibility mode.
- Metrics số records còn legacy.
- Chính sách chọn kết quả nếu cả hai forms cùng tồn tại.
- Giới hạn quyền và performance của query mở rộng.

Không để dual-format tồn tại vô thời hạn nếu nó làm mọi truy vấn phải xử lý hai kiểu dữ liệu.

## 41. Những lỗi Java Driver thường gặp

| Lỗi/triệu chứng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| `ClassCastException` khi `getString("_id")` | Field BSON ObjectId, không phải String | Dùng `getObjectId()` |
| Query bằng chuỗi hex không tìm thấy | `_id` lưu ObjectId | Parse `new ObjectId(hex)` |
| UUID encoding error | `UuidRepresentation.UNSPECIFIED`/codec không phù hợp | Cấu hình STANDARD hoặc legacy đúng nguồn |
| UUID đọc khác UUID đã viết | Byte order/subtype legacy mismatch | Xác định subtype và representation thực |
| UUID String query không khớp | Field Binary subtype 4 | Query bằng UUID đã được encode đúng |
| `CodecConfigurationException` với POJO | Thiếu/không nhận diện POJO codec | Đăng ký PojoCodecProvider/conventions |
| `BigDecimal` không lưu được Decimal128 | Vượt precision/exponent | Validate range/scale, rounding policy |
| Số tiền có sai số | Đã qua `double` | Parse string decimal/BigDecimal, không cast mù |
| `Decimal128.bigDecimalValue()` lỗi | Giá trị đặc biệt hoặc không phù hợp | Xử lý NaN/Infinity và validate domain |
| `getDate("createdAt")` trả null | Field missing/null hoặc sai mapping | Kiểm tra BSON type và presence |
| Giờ hiển thị lệch 7 tiếng | UTC instant được render ở zone khác | Phân biệt storage instant và display zone |
| LocalDate bị lùi một ngày | Dùng midnight UTC cho date-only rồi render timezone âm | Chọn date-only schema/convention |
| Mất nanoseconds | BSON DateTime chỉ milliseconds | Giới hạn precision hoặc thêm field |
| `Filters.eq(field,null)` trả cả field missing | MongoDB null equality semantics | Dùng `$type:10` hoặc `$exists` |
| `Updates.set(field,null)` không xóa field | Set BSON Null khác unset | Dùng `Updates.unset()` khi muốn xóa |
| POJO property null không thấy field | Codec/convention omit null | Kiểm tra serialization policy |
| Primitive `int` trở thành 0 | Không biểu diễn missing/null | Dùng `Integer` và presence policy |
| Unique index vẫn cho hai logical UUID tương đương | UUID subtype/representation khác | Chuẩn hóa format trước/ngoài migration |
| API JSON làm mất Decimal128 | Serializer biến Decimal thành Number | Dùng decimal string/Extended JSON contract |

## 42. Bài tập có đáp án

### Bài 1. ObjectId hay String?

Collection có `_id: ObjectId("65f000000000000000000101")`. Truy vấn Java dùng:

```java
Filters.eq("_id", "65f000000000000000000101")
```

có chắc tìm được không?

**Đáp án:** Không. String và BSON ObjectId là hai types khác nhau. Parse hex thành `ObjectId` và truyền ObjectId vào filter.

### Bài 2. Đọc `_id`

`Document.getString("_id")` gặp ClassCastException nhưng dữ liệu có ID. Nguyên nhân?

**Đáp án:** `_id` được decode thành `ObjectId`. Dùng `getObjectId("_id")` hoặc kiểm tra type trước khi đọc.

### Bài 3. Timestamp trong ObjectId

Có thể dùng `ObjectId.getDate()` làm thời gian hoàn tất thanh toán chính xác đến milliseconds không?

**Đáp án:** Không. Timestamp ObjectId có độ phân giải giây và thời điểm tạo ID không nhất thiết là thời điểm nghiệp vụ. Lưu `paidAt` BSON DateTime riêng.

### Bài 4. UUID subtype

Java UUID được mã hóa theo `STANDARD`. BSON binary subtype kỳ vọng?

**Đáp án:** **Subtype 4**. Legacy UUID thường dùng subtype 3 với representation riêng.

### Bài 5. UUID khác format

Field `requestId` lưu BSON Binary UUID nhưng API query bằng `UUID.toString()`. Vì sao không match?

**Đáp án:** Query truyền String BSON, trong khi field là Binary BSON. Cần UUID codec/representation thống nhất.

### Bài 6. Legacy UUID

Một field subtype 3 được tạo bởi driver cũ. Có thể gắn subtype 4 trực tiếp mà không đổi bytes không?

**Đáp án:** Không nên. Phải biết legacy representation và decode/re-encode đúng logical UUID. Byte order có thể khác.

### Bài 7. BigDecimal

`new BigDecimal(0.1)` có tương đương `new BigDecimal("0.1")` về exact decimal value không?

**Đáp án:** Không. Constructor từ `double` nhận giá trị binary approximation; dùng string decimal hoặc conversion policy chính xác.

### Bài 8. Decimal128 precision

Một `BigDecimal` có 40 chữ số có nghĩa. Có chắc Decimal128 lưu chính xác nguyên vẹn không?

**Đáp án:** Không. Decimal128 có giới hạn 34 significant decimal digits; cần kiểm tra khả năng biểu diễn và rounding policy.

### Bài 9. Decimal128 ↔ BigDecimal

Đọc `Decimal128` thành `double` rồi tạo `BigDecimal` có phải đường bảo toàn số tiền tốt nhất?

**Đáp án:** Không. Dùng `Decimal128.bigDecimalValue()` đối với số hữu hạn và tránh trung gian binary double.

### Bài 10. BigDecimal.equals

Vì sao `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là false?

**Đáp án:** `equals()` còn xét scale. Nếu domain chỉ cần so giá trị số, dùng `compareTo()==0`.

### Bài 11. Date timezone

Database lưu `ISODate("2026-11-14T08:00:00Z")`; người dùng UTC+07 thấy 15:00. Dữ liệu có bị đổi không?

**Đáp án:** Không. Đó là cùng instant được hiển thị ở hai timezone.

### Bài 12. LocalDateTime

`LocalDateTime.of(2026,11,14,9,0)` có tự xác định một UTC instant không?

**Đáp án:** Không. Cần ZoneId/offset hoặc một convention. Ví dụ `Asia/Ho_Chi_Minh` cho kết quả 02:00 UTC ngày đó.

### Bài 13. Precision

Ghi `Instant.parse("2026-11-14T08:15:30.123456789Z")` vào BSON DateTime. Có giữ đủ nanoseconds không?

**Đáp án:** Không. BSON DateTime lưu milliseconds; phần sub-millisecond bị mất theo conversion.

### Bài 14. Date-only

Ngày sinh `1995-07-21` có nên coi là UTC midnight instant trong mọi API không?

**Đáp án:** Không mặc định. Đây là date-only semantic; chọn lưu ISO string hoặc codec/convention rõ ràng để tránh timezone shift.

### Bài 15. Null equality

`{nickname:null}` trong MongoDB có chỉ match document có field BSON Null không?

**Đáp án:** Không. Nó cũng match documents thiếu field `nickname` theo null equality semantics.

### Bài 16. Chỉ BSON null

Muốn tìm field `nickname` có type BSON null nhưng không gồm missing, dùng gì?

**Đáp án:** `{nickname: {$type: 10}}` hoặc filter Java tương đương `Filters.type("nickname", BsonType.NULL)`.

### Bài 17. Field không tồn tại

Muốn tìm documents không có field `nickname`, dùng:

```javascript
{ nickname: { $exists: false } }
```

**Đáp án:** Đúng. `$exists:false` khác equality null.

### Bài 18. Set và unset

Sự khác nhau giữa `Updates.set("nickname", null)` và `Updates.unset("nickname")`?

**Đáp án:** Set ghi BSON Null vào field; unset xóa field khỏi document.

### Bài 19. `Document.containsKey`

Một `Document` có `note:null` và một document khác không có key `note`. `get("note")` có thể phân biệt được không?

**Đáp án:** Không vì cả hai trả Java null. Cần `containsKey("note")` hoặc kiểm tra BSON type.

### Bài 20. Wrapper types

POJO dùng primitive `int age`. Nếu field age không tồn tại, có thể phân biệt với tuổi bằng 0 không?

**Đáp án:** Không chỉ dựa trên primitive; giá trị mặc định 0. Dùng `Integer`/presence metadata và policy phù hợp.

### Bài 21. Validator

Validator có `required:["nickname"]` và `bsonType:["string","null"]`. Document thiếu nickname có hợp lệ không?

**Đáp án:** Không. `required` đòi field tồn tại; BSON null được phép nhưng missing không được phép.

### Bài 22. Time range

Vì sao query events trong một ngày thường dùng `createdAt >= start` và `createdAt < nextDayStart` thay vì `<= 23:59:59.999`?

**Đáp án:** Khoảng nửa mở dễ xử lý biên, precision và thời gian ngày lịch theo timezone; không phụ thuộc một giá trị “giây cuối cùng” cố định.

### Bài 23. JSON API

REST API trả Decimal128 dạng JSON number và frontend dùng JavaScript Number. Rủi ro?

**Đáp án:** Có thể mất precision vì Number dựa trên binary floating point. Cân nhắc decimal string/Extended JSON hoặc contract có parser decimal-aware.

### Bài 24. Mixed type

`payments.orderId` có cả String và ObjectId. Một filter ObjectId duy nhất có chắc thấy tất cả payments không?

**Đáp án:** Không. Cần khảo sát và migration schema/references, hoặc tạm dùng dual-read có điều kiện và mốc kết thúc rõ.

### Bài 25. Round-trip UUID

Ứng dụng mới muốn chuyển từ UUID subtype 3 sang subtype 4. Test tối thiểu cần xác nhận gì?

**Đáp án:** Logical UUID trước/sau, subtype, byte-order/legacy representation, uniqueness/index, related references và tương thích với writers cũ.

### Bài 26. Chọn data model

Ứng dụng lưu tổng tiền VND dạng 125000.50, thời điểm thanh toán UTC và transaction ID UUID. Chọn Java/BSON types hợp lý?

**Đáp án:** Có thể dùng `BigDecimal`/Decimal128 cho số tiền, `Instant`/BSON DateTime cho instant, `UUID`/Binary subtype 4 STANDARD cho request ID và `ObjectId` cho MongoDB document ID nếu schema chọn ObjectId. Nên ghi rõ rounding/currency/timezone/UUID representation.

## 43. Checklist trước khi đưa vào production

### ID và UUID

- [ ] Xác định kiểu BSON thật của `_id` và các reference fields.
- [ ] Chuyển hex string sang ObjectId đúng lúc ở API boundary nếu schema dùng ObjectId.
- [ ] Không dựa vào timestamp ObjectId thay business timestamps.
- [ ] Cấu hình `UuidRepresentation` rõ ràng cho UUID Binary.
- [ ] Đánh giá subtype 3/4 và byte ordering nếu có dữ liệu legacy.
- [ ] Không trộn UUID String và UUID Binary không có kế hoạch.
- [ ] Kiểm tra unique index và references sau migration ID.

### Decimal128

- [ ] Dùng `BigDecimal`/`Decimal128` theo schema, tránh `double` cho số tiền chính xác.
- [ ] Không tạo BigDecimal từ binary double không cần thiết.
- [ ] Kiểm tra precision/exponent/range trước khi encode Decimal128.
- [ ] Chọn rounding mode, currency, scale và cách xử lý NaN/Infinity.
- [ ] Thống nhất numeric types giữa dữ liệu, queries, updates và aggregations.
- [ ] Kiểm tra API JSON không làm mất precision ngoài ý muốn.

### Ngày giờ

- [ ] Dùng BSON DateTime cho instants theo epoch milliseconds UTC.
- [ ] Hiểu loss of precision nếu Java Instant có nanoseconds.
- [ ] Tách `LocalDate` date-only khỏi instant.
- [ ] Không chuyển `LocalDateTime` sang UTC nếu chưa biết ZoneId/offset.
- [ ] Nếu cần nhớ timezone gốc, lưu zone ID riêng.
- [ ] Tạo range query theo boundary timezone và khoảng nửa mở.
- [ ] Không nhầm epoch seconds với epoch milliseconds.

### Null, schema và codecs

- [ ] Định nghĩa rõ field missing, BSON Null và empty string khác nhau thế nào.
- [ ] Dùng `Document.containsKey` hoặc BSON type khi cần phân biệt missing.
- [ ] Không quên `Filters.eq(field,null)` match null hoặc missing.
- [ ] Phân biệt `Updates.set(...,null)` và `Updates.unset(...)`.
- [ ] Dùng wrapper type khi cần biểu diễn null/missing thay vì primitive.
- [ ] Kiểm tra POJO codec có omit null property hay không.
- [ ] Validator `required` và `bsonType` khớp hợp đồng dữ liệu.
- [ ] Ghi nhận codec registry, Java Driver version và UUID representation.
- [ ] Có round-trip tests và truy vấn `$type` cho các BSON fields quan trọng.
- [ ] Có data migration/backup/rollback khi chuyển types.

## 44. Tổng kết

**BSON type là một phần của hợp đồng dữ liệu** giữa MongoDB và ứng dụng Java. `ObjectId` khác chuỗi 24 ký tự; `UUID` có thể được lưu dưới dạng Binary subtype 4 STANDARD hoặc những legacy subtype 3, và việc chọn sai representation có thể làm query/unique key bị lệch dù logical UUID giống nhau. `Decimal128` giúp lưu số thập phân với độ chính xác cao, nhưng Java `BigDecimal` vẫn cần kiểm soát precision, scale và rounding; đưa số tiền qua `double` là một lỗi thường gặp.

Với thời gian, BSON DateTime là **milliseconds kể từ Unix epoch UTC**, không lưu timezone name và không giữ độ chính xác nanoseconds của `Instant`. `LocalDate` biểu diễn ngày lịch, còn `LocalDateTime` chưa xác định được instant nếu thiếu timezone. Query theo ngày phải dựa trên ranh giới múi giờ nghiệp vụ, không chỉ cắt chuỗi timestamp.

Với giá trị trống, **BSON Null khác field missing**. Java `Document.get()` có thể trả null cho cả hai, nên cần `containsKey`/`$exists`/`$type` khi nghiệp vụ yêu cầu phân biệt. `Updates.set(field,null)` không giống `unset(field)`, và POJO codec có thể chọn omit null property theo conventions.

Khi triển khai Java Driver, nên xác định **type mapping ngay từ schema**, cấu hình codec/UUID rõ ràng, dùng round-trip tests để xác nhận BSON thực lưu và kiểm soát migration dữ liệu cũ. Dữ liệu chỉ đáng tin cậy khi **kiểu lưu, kiểu Java, query, validator và API contract** đều thống nhất.

### Tài liệu tham khảo chính thức

- [MongoDB Java Sync Driver — BSON and Data Formats](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/)
- [MongoDB Java Sync Driver — POJOs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/pojo-customization/)
- [MongoDB Java Sync Driver — UUIDs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/uuid/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [Java SE — java.time.Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
