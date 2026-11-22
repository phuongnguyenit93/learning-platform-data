# Kiểu BSON và khả năng biểu diễn tương ứng trong Java

MongoDB lưu document theo định dạng **BSON (Binary JSON)**. BSON có nhiều kiểu dữ liệu hơn JSON thông thường: ngoài chuỗi, số, boolean, mảng và object, nó còn có `ObjectId`, số nguyên 32/64 bit, `Decimal128`, ngày giờ, dữ liệu nhị phân và một số kiểu phục vụ hệ thống. Khi sử dụng **Spring Data MongoDB**, Java object được chuyển sang BSON trước khi ghi và được dựng lại khi đọc bằng `MappingMongoConverter` cùng các converter/codec liên quan.

Việc chọn sai kiểu có thể gây mất độ chính xác của tiền tệ, lỗi tràn số, truy vấn `_id` không khớp, sai múi giờ hoặc dữ liệu được lưu khác với schema mà ứng dụng dự kiến. Bài thuộc chương **Kiểu dữ liệu** này xây dựng nền tảng để bạn thiết kế field, truy vấn, index, aggregation, transaction và kiểm thử dữ liệu qua `MongoRepository` hoặc `MongoTemplate`.

Sau bài học, bạn có thể:

- Đọc một giá trị BSON và chọn kiểu Java phù hợp khi làm việc với Spring Data MongoDB.
- Phân biệt `int32`, `int64`, `double`, `decimal128` và giới hạn độ chính xác của từng kiểu.
- Lựa chọn cách lưu ngày giờ, `ObjectId`, UUID/Binary, nested document và mảng.
- Phân biệt **field không tồn tại**, **field có giá trị `null`** và **giá trị mặc định của Java primitive**.
- Kiểm tra kiểu BSON bằng `mongosh`, Extended JSON và `$type`, sau đó đối chiếu với dữ liệu đọc qua Java.
- Nhận diện những chỗ Spring Data cần annotation hoặc converter tường minh.

## 1. BSON, JSON và object Java là ba lớp biểu diễn khác nhau

Một document MongoDB có thể được mô tả như sau trong `mongosh`:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  title: "Java với MongoDB",
  edition: NumberInt(2),
  views: NumberLong("9007199254740993"),
  price: NumberDecimal("129000.50"),
  active: true,
  publishedAt: ISODate("2026-01-15T08:30:00Z"),
  tags: ["java", "mongodb"],
  author: { name: "Lan", country: "VN" }
}
```

Đây là **cú pháp biểu diễn dành cho MongoDB Shell**, không phải JSON thuần. Chẳng hạn, JSON không có hàm `ObjectId(...)` hoặc `ISODate(...)`. Khi dùng Java:

1. Ứng dụng tạo object chứa các kiểu như `String`, `Integer`, `Long`, `BigDecimal`, `Instant`.
2. Bộ ánh xạ Spring Data chuyển các thuộc tính thành BSON theo quy tắc mặc định và metadata của entity.
3. MongoDB lưu các giá trị BSON; truy vấn, index và aggregation hoạt động trên **kiểu BSON thực tế**.
4. Khi đọc, Spring Data chuyển BSON về các kiểu Java được khai báo trong domain class.

Đừng suy ra kiểu BSON từ cách JSON được hiển thị trong REST API, logger hoặc Compass. Ví dụ Java `Long` và `Integer` đều có thể được serialize thành cùng một chuỗi số trong JSON, dù BSON lưu lần lượt là `long` và `int`.

### Extended JSON (EJSON) để truyền tải có giữ thông tin kiểu

Extended JSON dùng các marker đặc biệt nhằm biểu diễn các kiểu BSON trong văn bản JSON:

```json
{
  "_id": { "$oid": "665f1f2a4b6c7d8e9f001234" },
  "edition": { "$numberInt": "2" },
  "views": { "$numberLong": "9007199254740993" },
  "price": { "$numberDecimal": "129000.50" },
  "publishedAt": { "$date": "2026-01-15T08:30:00Z" }
}
```

Đây là ví dụ **Canonical/Extended JSON**, không có nghĩa document đã lưu các trường `$oid`, `$date` hay `$numberLong` dưới dạng object thông thường. Các marker mô tả kiểu khi chuyển BSON sang biểu diễn văn bản. `mongosh`, MongoDB Compass và một số công cụ xuất/nhập có thể hiển thị các dạng EJSON khác nhau (chẳng hạn Relaxed hoặc Canonical). Nếu dùng parser JSON thông thường mà không hiểu EJSON, bạn có thể biến sai kiểu thành object lồng nhau.

## 2. Bảng đối chiếu BSON và Java

Bảng sau là **định hướng mapping phổ biến**, không phải cam kết mọi driver/framework đều tự ánh xạ như nhau. Spring Data MongoDB, MongoDB Java Driver, POJO codecs, converter tùy biến và cấu hình UUID có thể có các quy tắc khác nhau.

| Kiểu BSON | Ví dụ trong mongosh | Kiểu Java thường dùng | Lưu ý |
| --- | --- | --- | --- |
| **String** | `"MongoDB"` | `String` | Dữ liệu UTF-8; chú ý collation, tìm kiếm và độ dài |
| **Boolean** | `true` | `Boolean`, `boolean` | Wrapper cho phép biểu diễn thiếu/`null` |
| **Int32** (alias `int`) | `NumberInt(42)` | `Integer`, `int` | Phạm vi số nguyên có dấu 32 bit |
| **Int64** (alias `long`) | `NumberLong("42")` | `Long`, `long` | Phạm vi số nguyên có dấu 64 bit |
| **Double** | `1.25` | `Double`, `double` | IEEE 754 nhị phân, có sai số biểu diễn thập phân |
| **Decimal128** (alias `decimal`) | `NumberDecimal("19.90")` | `BigDecimal`, `Decimal128` | Giữ số thập phân với tối đa 34 chữ số có nghĩa; Spring Data có thể cần `@Field(targetType = FieldType.DECIMAL128)` |
| **ObjectId** | `ObjectId("...")` | `org.bson.types.ObjectId`; đôi khi `String` với conversion | Giá trị BSON 12 byte; biểu diễn hex 24 ký tự chỉ là dạng văn bản |
| **Date** | `ISODate("2026-01-15T08:30:00Z")` | `Date`, `Instant` | Mốc thời gian UTC theo mili giây từ epoch; không giữ múi giờ gốc |
| **Timestamp** | Kiểu timestamp BSON | `org.bson.BsonTimestamp` (hoặc kiểu driver tương ứng) | Gồm thời gian và increment; chủ yếu dành cho cơ chế nội bộ/oplog |
| **Binary** (alias `binData`) | `BinData(...)`, `UUID("...")` | `byte[]`, `org.bson.types.Binary`, `UUID` | Cần thống nhất subtype/UUID representation |
| **Null** | `null` | `null` của reference type | Khác field bị thiếu, và khác giá trị mặc định của primitive |
| **Array** | `["a", "b"]` | `List<T>`, `Set<T>` hoặc mảng Java khi mapping hỗ trợ | Mỗi phần tử có thể mang một kiểu BSON khác nhau |
| **Document/Object** | `{ city: "Ha Noi" }` | POJO lồng nhau, `Map<String, ?>`, `Document` | Phù hợp cho nested object; chú ý key và metadata loại |
| **Regular Expression** | `/mongo/i` | `Pattern`, `BsonRegularExpression` | Regex BSON dùng cho truy vấn; không đồng nghĩa text index |
| **JavaScript Code** | Kiểu Code BSON | `org.bson.types.Code` | Kiểu đặc biệt, thường không nên dùng trong domain mới |
| **MinKey / MaxKey** | `MinKey()` / `MaxKey()` | `org.bson.types.MinKey` / `MaxKey` | Giá trị chuyên biệt phục vụ so sánh/sắp xếp và truy vấn |

Một số kiểu BSON cũ như **Undefined**, **Symbol**, **DBPointer** hoặc **JavaScript code with scope** có tính lịch sử hoặc đã bị loại bỏ/không khuyến khích trong thiết kế mới. Bạn có thể gặp chúng khi đọc dữ liệu cũ, nhưng không nên đưa vào domain mới nếu không có lý do tương thích cụ thể. `DBRef` là quy ước biểu diễn tham chiếu theo bộ field đặc biệt, cần phân biệt với kiểu BSON **DBPointer** đã lỗi thời.

### Chọn kiểu theo nhu cầu nghiệp vụ

| Dữ liệu | Ưu tiên cân nhắc | Tránh |
| --- | --- | --- |
| Số lượng tồn kho, số lượt xem | `int` hoặc `long` nếu giá trị nguyên và trong phạm vi | `double` cho bộ đếm chính xác |
| Tiền tệ | Số nguyên ở đơn vị nhỏ nhất **hoặc** `Decimal128` với quy tắc làm tròn | `double` cho phép tính cần độ chính xác thập phân |
| Ngày giờ tạo/sửa record | `Instant`/BSON Date; lưu thời điểm theo UTC | Diễn giải một chuỗi ngày giờ không múi giờ thành timestamp tùy ý |
| Định danh kỹ thuật | `ObjectId` hoặc UUID theo quy ước hệ thống | Trộn String/ObjectId/UUID Binary trong cùng field |
| Mã định danh nghiệp vụ | `String` và ràng buộc uniqueness phù hợp | Giả định chuỗi hex tự động là ObjectId |
| Nhãn có thể bỏ trống | `String` nullable, quy tắc rõ về missing/null | Dùng primitive để nhận biết không có giá trị |
| Cấu trúc con thuộc cùng aggregate | Embedded document/list có giới hạn kích thước | Nhúng mảng tăng vô hạn |

## 3. Nhóm số: Int32, Int64, Double và Decimal128

### 3.1. Phạm vi số nguyên và nguy cơ tràn

| Kiểu | Phạm vi / đặc tính | Java |
| --- | --- | --- |
| BSON Int32 | Từ `-2,147,483,648` đến `2,147,483,647` | `Integer`/`int` |
| BSON Int64 | Từ `-9,223,372,036,854,775,808` đến `9,223,372,036,854,775,807` | `Long`/`long` |
| BSON Double | Số dấu chấm động 64 bit; khoảng 15–17 chữ số thập phân có nghĩa | `Double`/`double` |
| BSON Decimal128 | Số thập phân 128 bit; độ chính xác tối đa 34 chữ số thập phân có nghĩa trong phạm vi exponent của Decimal128 | `BigDecimal`/`Decimal128` |

Trong `mongosh`, khi cần xác định rõ số được ghi ở kiểu nào, dùng constructor BSON:

```javascript
const sample = {
  quantity: NumberInt(125),
  totalViews: NumberLong("9007199254740993"),
  rating: 4.5,
  amount: NumberDecimal("19999999.99")
};
```

Giá trị `9007199254740993` lớn hơn số nguyên an toàn tối đa của JavaScript `Number` (`2^53 - 1`). Vì vậy hãy truyền chuỗi vào `NumberLong("...")`, thay vì tạo literal JavaScript rồi mới chuyển đổi. Trong Java, `Long` biểu diễn chính xác giá trị này, miễn là vẫn nằm trong phạm vi 64 bit.

Nếu Java entity dùng `int` để nhận số trong DB vượt giới hạn Int32, quá trình đọc/chuyển đổi có thể thất bại hoặc gây sai lệch tùy đường chuyển đổi. Khi counter có khả năng vượt 2,1 tỷ, cân nhắc `long` ngay từ thiết kế.

### 3.2. Tại sao không dùng `double` cho số tiền?

Nhiều phân số thập phân không biểu diễn chính xác trong hệ nhị phân. Trong Java:

```java
double total = 0.1 + 0.2;
System.out.println(total == 0.3); // false

java.math.BigDecimal correct =
    new java.math.BigDecimal("0.1")
        .add(new java.math.BigDecimal("0.2"));
System.out.println(correct); // 0.3
```

Hai chiến lược phổ biến cho tiền:

1. **Lưu số nguyên ở đơn vị nhỏ nhất**: chẳng hạn `amountMinor = 159900L` với đồng tiền có hai chữ số thập phân, tương đương 1.599,00 đơn vị chính (tùy quy ước). Ứng dụng phải lưu `currency` và định nghĩa scale cho từng đơn vị tiền.
2. **Lưu BSON Decimal128**: phù hợp khi cần thao tác trực tiếp bằng số thập phân trong MongoDB; khi đi qua Spring Data dùng `BigDecimal` kết hợp metadata hoặc converter để chủ động chọn kiểu lưu.

Ví dụ với Spring Data MongoDB:

```java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Field(targetType = FieldType.DECIMAL128)
private BigDecimal unitPrice;
```

Trong nhiều cấu hình Spring Data MongoDB, `BigDecimal` có thể được biểu diễn mặc định bằng **BSON String** để tránh chuyển đổi làm mất dữ liệu. `@Field(targetType = FieldType.DECIMAL128)` làm rõ rằng cần lưu **BSON Decimal128**. Kiểu Decimal128 không lưu mọi `BigDecimal` có precision/scale bất kỳ; cần kiểm tra phạm vi và quy tắc làm tròn trước khi ghi.

**Bẫy khác:** `new BigDecimal(0.1)` lấy giá trị gần đúng đã bị làm tròn của `double`. Khi nhận hằng số thập phân, dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)`. Khi tổng hợp nhiều khoản tiền, xác định scale, rounding mode và chính sách tiền tệ từ đầu.

### 3.3. So sánh, cộng số và aggregation

MongoDB có hỗ trợ so sánh các kiểu số với nhau trong nhiều phép so sánh/truy vấn, nhưng kết quả không thể loại bỏ những vấn đề về precision đã phát sinh. Phép toán có thể làm thay đổi kiểu hoặc gặp tràn số tùy toán tử và giá trị. Đừng xem "so sánh được" là bằng chứng nên trộn Int32/Int64/Double/Decimal128 trong cùng field nghiệp vụ.

Ví dụ kiểm tra trường tiền đang lưu ở loại BSON nào:

```javascript
db.catalog_items.aggregate([
  { $project: { _id: 0, priceType: { $type: "$unitPrice" } } },
  { $limit: 10 }
]);
```

Nếu collection chứa một số document có `unitPrice` là String và số khác là Decimal128, hãy ưu tiên **migrating và chuẩn hóa dữ liệu** theo kế hoạch trước khi viết pipeline tính tổng. Một chuỗi `"199.90"` không tự biến thành Decimal128 chỉ vì Java entity khai báo `BigDecimal`.

## 4. Ngày giờ: BSON Date khác BSON Timestamp

### 4.1. BSON Date mang một *instant*

MongoDB BSON Date lưu số mili giây có dấu tính từ Unix epoch 1970-01-01T00:00:00Z. Giá trị là **một thời điểm**, không giữ thông tin múi giờ người dùng đã nhập.

```javascript
const date = ISODate("2026-01-15T08:30:00Z");
db.bson_dates_demo.insertOne({
  createdAt: date,
  description: "Ngày giờ thử nghiệm"
});
```

Trong Java, các kiểu phù hợp:

```java
import java.time.Instant;
import java.util.Date;

Instant createdAt = Instant.parse("2026-01-15T08:30:00Z");
Date legacyDate = Date.from(createdAt);
```

`Instant` biểu diễn thời điểm độc lập múi giờ. Nếu ứng dụng nhận `LocalDateTime` như "15/01/2026 15:30" thì **chưa đủ thông tin** để xác định instant: cần zone/offset. Java `LocalDateTime` không chứa offset, nên việc chuyển nó sang BSON Date phải theo một chính sách rõ ràng; những phiên bản/cấu hình converter khác nhau có thể dùng quy tắc múi giờ khác nhau.

Nếu bài toán cần lưu *ngày sinh* hoặc *ngày nghỉ lễ theo địa phương*, một BSON Date tại nửa đêm UTC chưa chắc biểu diễn đúng ý nghĩa. Có thể lưu ngày dạng `YYYY-MM-DD` hay cấu trúc ngày riêng theo hợp đồng dữ liệu, hoặc dùng converter được kiểm soát. Với lịch họp, nên lưu instant và zone ID khi cần tái dựng giờ địa phương chính xác.

**Độ phân giải:** BSON Date ở mức **mili giây**. `Instant` của Java có thể giữ nanosecond; nếu cần tính chính xác cao hơn mili giây, việc ghi/đọc qua BSON Date có thể làm mất phần độ chính xác đó.

### 4.2. BSON Timestamp không thay cho `createdAt`

Kiểu BSON Timestamp chứa phần thời gian (tính bằng giây) và bộ đếm tăng. MongoDB dùng nó trong các cơ chế như oplog và replication. Đừng dùng nó cho trường ngày giờ nghiệp vụ thông thường chỉ vì tên là "Timestamp". Hãy chọn BSON Date cho `createdAt`, `updatedAt` hoặc thời điểm sự kiện nếu không có lý do chuyên biệt khác.

### 4.3. Những lựa chọn Java và rủi ro

| Kiểu Java | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| `Instant` | Thời điểm sự kiện chính xác theo UTC | BSON Date có độ phân giải mili giây |
| `java.util.Date` | Tương thích API cũ | Mutable; nên hạn chế trong domain mới nếu có thể |
| `LocalDateTime` | Ngày giờ địa phương chưa gắn zone | Phải xác định zone khi chuyển sang một instant |
| `LocalDate` | Ngày theo lịch | Không tự suy ra offset/múi giờ; cần hợp đồng lưu rõ ràng |
| `OffsetDateTime` / `ZonedDateTime` | Cần giữ offset hoặc zone | BSON Date không giữ metadata zone gốc; dùng cấu trúc bổ sung/converter nếu cần |

## 5. ObjectId, String ID và UUID/Binary

### 5.1. ObjectId là một kiểu BSON độc lập

`ObjectId` dài 12 byte và thường hiển thị dưới dạng 24 ký tự hexadecimal:

```javascript
const id = new ObjectId();
print(id.toHexString());
print(id.getTimestamp()); // Phần timestamp trong ObjectId
```

Timestamp nhúng trong ObjectId chỉ có độ phân giải **giây**, và ID có thể được tạo trước khi document được lưu. Nó không thay thế field `createdAt` chính thức.

Hai document sau có hai giá trị `_id` **khác kiểu** ngay cả khi phần ký tự giống nhau:

```javascript
const hex = "665f1f2a4b6c7d8e9f001234";
db.id_type_demo.insertOne({ _id: new ObjectId(hex), kind: "oid" });
db.id_type_demo.insertOne({ _id: hex, kind: "string" });

db.id_type_demo.findOne({ _id: new ObjectId(hex) }); // kind "oid"
db.id_type_demo.findOne({ _id: hex });               // kind "string"
```

Với Spring Data MongoDB, có thể khai báo:

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {
    @Id
    private ObjectId id;
    private String name;
}
```

`@Id ObjectId id` ánh xạ trực tiếp tới `_id` kiểu ObjectId. `@Id String id` thường có quy tắc chuyển String 24 hex hợp lệ thành ObjectId khi có thể; vì vậy kiểu Java String **không tự bảo đảm** BSON String. Nếu cần luôn giữ chuỗi là chuỗi, cân nhắc `@MongoId String id` và định nghĩa cách cấp ID rõ ràng. Generic ID của repository phải nhất quán với kiểu Java được khai báo.

### 5.2. UUID thường lưu dưới BSON Binary

`java.util.UUID` không phải BSON String theo mặc định về mặt khái niệm. Thông thường UUID được lưu thành **BSON Binary subtype 4 (standard UUID)** khi driver/codec được cấu hình tương ứng. Hệ thống cũ có thể dùng các biến thể subtype 3 và thứ tự byte khác nhau.

Trước khi trao đổi UUID giữa Java Driver, Spring Data MongoDB, dịch vụ khác hoặc migrate dữ liệu:

- Chốt định dạng lưu: UUID dạng BSON Binary chuẩn hay UUID dạng String.
- Với BSON Binary, thống nhất `UuidRepresentation.STANDARD` (hoặc representation khác nếu có yêu cầu tương thích legacy) trên các đường đọc/ghi.
- Thực hiện kiểm thử ghi–đọc và truy vấn theo UUID thực tế; không chỉ so sánh chuỗi hiển thị.
- Khi chuyển từ dữ liệu legacy, phải xét subtype lẫn byte order trước khi chuyển đổi.

Một BSON Binary cũng có thể lưu `byte[]` cho dữ liệu nhỏ. Không nên nhúng file rất lớn vào document: MongoDB giới hạn **16 MiB/document**; với dữ liệu tệp lớn có thể xem xét GridFS hoặc object storage tùy thiết kế.

## 6. Document lồng nhau, mảng, Map và enum

MongoDB lưu cấu trúc object lồng nhau bằng BSON Document, và tập phần tử bằng BSON Array:

```javascript
{
  sku: "BK-101",
  publisher: {
    name: "NXB Ví dụ",
    address: { city: "Ha Noi", country: "VN" }
  },
  tags: ["java", "mongodb"],
  dimensionsCm: [12.5, 18.0, 2.0],
  status: "ACTIVE"
}
```

Java class có thể mô hình hóa:

```java
import java.util.List;
import java.util.Map;

class BookDetails {
    private Publisher publisher;
    private List<String> tags;
    private List<Double> dimensionsCm;
    private Map<String, String> attributes;
    private BookStatus status;
}

class Publisher {
    private String name;
    private Address address;
}

class Address {
    private String city;
    private String country;
}

enum BookStatus {
    ACTIVE, ARCHIVED
}
```

Đây là **minh họa cấu trúc**: để dùng thực tế cần constructor/getter/setter hoặc cơ chế construction của Spring Data tương ứng. Spring Data MongoDB có thể ánh xạ object thường thành nested document, list thành BSON array, và enum thường thành tên hằng chuỗi nếu không cấu hình converter khác.

Điểm cần cân nhắc:

- **Array có thứ tự**. `List<T>` phù hợp khi thứ tự phần tử có ý nghĩa; `Set<T>` có ngữ nghĩa tập hợp và không bảo đảm cùng quy tắc thứ tự như List.
- BSON array có thể chứa các kiểu khác nhau, nhưng domain Java dạng `List<String>` chỉ mong đợi phần tử String. Dữ liệu ngoại lai không hợp đồng có thể gây lỗi mapping.
- `Map<String, ?>` phù hợp cho thuộc tính động, nhưng key phải tuân theo các quy tắc hợp lệ/escape của BSON và lớp mapping. Kiểm thử kỹ key chứa dấu chấm (`.`), ký tự `$` hoặc các tên trường đặc biệt.
- **Document lồng nhau** tiện cho dữ liệu có chung vòng đời và cần cập nhật nguyên tử cùng root. Không nên nhúng danh sách tăng không giới hạn vào một document.
- Enum lưu dạng tên chuỗi dễ đọc nhưng **đổi tên enum constant** có thể làm hỏng khả năng đọc dữ liệu cũ; cân nhắc converter hoặc giá trị ổn định khi cần version hóa schema.

## 7. Null, missing và primitive mặc định

Đây là một trong những lỗi khó nhận ra khi chuyển dữ liệu BSON về Java.

Ba document sau mang ý nghĩa khác nhau:

```javascript
{ _id: 1, note: null }           // Trường note tồn tại, giá trị BSON Null
{ _id: 2 }                       // Trường note không tồn tại
{ _id: 3, note: "" }             // Trường note tồn tại, chuỗi rỗng
```

Trong MongoDB:

```javascript
// Khớp cả note = null và note không tồn tại:
db.notes.find({ note: null });

// Chỉ khớp field có giá trị BSON Null:
db.notes.find({ note: { $type: "null" } });

// Chỉ khớp field chưa tồn tại:
db.notes.find({ note: { $exists: false } });

// Khớp mọi document có field note, kể cả giá trị null:
db.notes.find({ note: { $exists: true } });
```

`$type` trong **aggregation expression** còn có thể trả chuỗi `"missing"` khi đường dẫn trường không tồn tại; trong khi điều kiện `$type` của truy vấn dùng để kiểm tra kiểu BSON cụ thể.

Khi ánh xạ vào Java:

| Java declaration | Giá trị khi MongoDB thiếu field (thường gặp) | Rủi ro |
| --- | --- | --- |
| `Integer stock` | `null` | Có thể biểu diễn "chưa biết" |
| `int stock` | `0` theo giá trị mặc định của primitive | Khó phân biệt dữ liệu vắng mặt với lượng tồn 0 |
| `Boolean active` | `null` | Biểu diễn trạng thái ba giá trị |
| `boolean active` | `false` theo giá trị mặc định primitive | Có thể biến trạng thái chưa thiết lập thành false |
| `String note` | `null` | Có thể mất khác biệt giữa missing và explicit null nếu không có cơ chế theo dõi hiện diện riêng |

Tùy constructor, default field initializer hoặc custom converter, giá trị thực tế sau khi đọc có thể khác các giá trị trong bảng. Không dùng bảng này như một hợp đồng thay thế cho kiểm thử mapping của ứng dụng.

Nếu ứng dụng cần phân biệt **missing / null / giá trị**, hãy thiết kế rõ mô hình dữ liệu hoặc dùng thao tác cập nhật theo field và quy tắc chuyển đổi riêng. Trường primitive trong Java không thể tự mang ba trạng thái đó.

Trong Spring Data MongoDB, hành vi mặc định khi ghi field `null` còn chịu ảnh hưởng của metadata và cấu hình mapping: field có thể bị bỏ qua khi ghi hoặc được ghi thành BSON Null khi được cấu hình phù hợp. `@Field(write = Field.Write.ALWAYS)` là một cách yêu cầu ghi cả giá trị null trong những phiên bản Spring Data hỗ trợ thuộc tính này; hãy kiểm tra phiên bản thư viện của dự án trước khi áp dụng. Để xóa hẳn field, dùng `$unset` chứ không mặc định xem `$set: { note: null }` là thao tác tương đương.

## 8. Tạo entity Spring Data MongoDB với kiểu lưu rõ ràng

Ví dụ một document hóa đơn nhỏ, dùng ID ObjectId, số tiền nguyên theo đơn vị nhỏ nhất và một khoản thuế Decimal128:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "bson_invoices")
public class Invoice {
    @Id
    private ObjectId id;

    private String invoiceNo;
    private long subtotalMinor;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal taxAmount;

    private Instant createdAt;
    private List<Line> lines = new ArrayList<>();

    @Version
    private Long version;

    protected Invoice() {}

    public Invoice(
            String invoiceNo, long subtotalMinor,
            BigDecimal taxAmount, Instant createdAt) {
        this.invoiceNo = invoiceNo;
        this.subtotalMinor = subtotalMinor;
        this.taxAmount = taxAmount;
        this.createdAt = createdAt;
    }

    public ObjectId getId() { return id; }
    public String getInvoiceNo() { return invoiceNo; }
    public long getSubtotalMinor() { return subtotalMinor; }
    public BigDecimal getTaxAmount() { return taxAmount; }
    public Instant getCreatedAt() { return createdAt; }

    public static class Line {
        private String sku;
        private int quantity;
        private long unitPriceMinor;

        protected Line() {}

        public Line(String sku, int quantity, long unitPriceMinor) {
            this.sku = sku;
            this.quantity = quantity;
            this.unitPriceMinor = unitPriceMinor;
        }
    }
}
```

Repository khai báo đúng kiểu ID:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface InvoiceRepository
        extends MongoRepository<Invoice, ObjectId> {
}
```

Ghi và đọc:

```java
Invoice newInvoice = new Invoice(
    "INV-001",
    125000L,
    new BigDecimal("12500.50"),
    Instant.parse("2026-01-15T08:30:00Z")
);

Invoice saved = invoiceRepository.insert(newInvoice);
Invoice loaded = invoiceRepository.findById(saved.getId())
    .orElseThrow(() -> new IllegalStateException("Không tìm thấy"));

System.out.println(loaded.getTaxAmount());
```

Trong BSON, các trường quan trọng dự kiến:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  invoiceNo: "INV-001",
  subtotalMinor: NumberLong("125000"),
  taxAmount: NumberDecimal("12500.50"),
  createdAt: ISODate("2026-01-15T08:30:00Z"),
  lines: [],
  version: NumberLong(0)
}
```

Đây là **kết quả mô tả**, không phải giá trị cố định: ID, version, field `_class` và cách hiển thị các số có thể khác theo cấu hình Spring Data/driver. `@Version` phục vụ optimistic locking qua những API ghi có hỗ trợ version; nó không làm mọi câu lệnh cập nhật tùy biến tự động kiểm tra phiên bản.

### Khi muốn điều khiển kiểu qua Java Driver trực tiếp

Nếu dùng `MongoTemplate` với mapping entity, converter Spring Data được áp dụng. Nếu dùng `org.bson.Document` hoặc `BsonDocument` qua driver ở cấp thấp hơn, bạn đang chủ động chọn cách biểu diễn BSON:

```java
import java.math.BigDecimal;
import java.util.Date;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;

Document raw = new Document("_id", new ObjectId())
    .append("invoiceNo", "INV-RAW-001")
    .append("subtotalMinor", 125000L)
    .append("taxAmount", new Decimal128(new BigDecimal("12500.50")))
    .append("createdAt", new Date());
```

`Document` ở ví dụ này là class của MongoDB Java Driver, **không phải annotation `@Document` của Spring Data**. Lệnh `append` tạo cấu trúc document phía client; để lưu cần collection/driver connection phù hợp. Với thao tác ghi thô, annotation của Java entity không tự chạy như khi qua `MappingMongoConverter`.

## 9. Thực hành quan sát từng loại BSON bằng mongosh

Tạo collection thực hành riêng và gắn marker để chỉ đọc/xóa dữ liệu của lần thử hiện tại:

```javascript
use spring_data_training

const lab = db.getCollection("bson_types_lab");
const runId = "data-types-001-" + new ObjectId().toHexString();

const result = lab.insertOne({
  runId: runId,
  textValue: "Xin chào BSON",
  boolValue: true,
  intValue: NumberInt(123),
  longValue: NumberLong("9007199254740993"),
  doubleValue: 0.1,
  decimalValue: NumberDecimal("0.10"),
  dateValue: ISODate("2026-01-15T08:30:00Z"),
  objectIdValue: new ObjectId(),
  uuidValue: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  nullValue: null,
  numbers: [NumberInt(1), NumberLong("2"), NumberDecimal("3.00")],
  nested: { enabled: true, tags: ["java", "bson"] }
});

printjson(result.insertedId);
```

Lệnh trên minh họa một record có nhiều kiểu. `UUID(...)` của mongosh tạo biểu diễn UUID chuẩn; nếu đang dùng shell/driver cũ không hỗ trợ cú pháp này, hãy kiểm tra phiên bản trước khi chạy hoặc bỏ riêng field `uuidValue`. Các kiểu số cố định được tạo bằng `NumberInt`, `NumberLong` và `NumberDecimal` để tránh bị suy diễn theo literal JavaScript.

### 9.1. Dùng `$type` để kiểm tra loại BSON

```javascript
lab.aggregate([
  { $match: { _id: result.insertedId, runId: runId } },
  {
    $project: {
      _id: 0,
      textType: { $type: "$textValue" },
      boolType: { $type: "$boolValue" },
      intType: { $type: "$intValue" },
      longType: { $type: "$longValue" },
      doubleType: { $type: "$doubleValue" },
      decimalType: { $type: "$decimalValue" },
      dateType: { $type: "$dateValue" },
      objectIdType: { $type: "$objectIdValue" },
      uuidType: { $type: "$uuidValue" },
      nullType: { $type: "$nullValue" },
      missingType: { $type: "$notPresent" },
      arrayType: { $type: "$numbers" },
      nestedType: { $type: "$nested" }
    }
  }
]).toArray();
```

Giá trị dự kiến của các trường là: `string`, `bool`, `int`, `long`, `double`, `decimal`, `date`, `objectId`, `binData`, `null`, `missing`, `array` và `object`. Lưu ý rằng tên `double` ở đây là **tên loại BSON**, không phải bằng chứng mọi phép tính liên quan đều có cùng độ chính xác như Decimal128.

### 9.2. Lọc theo đúng kiểu BSON

```javascript
lab.find({
  runId: runId,
  decimalValue: { $type: "decimal" }
}).toArray();

lab.find({
  runId: runId,
  nullValue: { $type: "null" }
}).toArray();

lab.find({
  runId: runId,
  notPresent: { $exists: false }
}).toArray();
```

Đối với mảng, query `$type` có thể kiểm tra cả phần tử bên trong mảng ở một số trường hợp, trong khi aggregation `$type` áp dụng lên **giá trị biểu thức** và trả về kiểu của cả mảng. Vì vậy, khi muốn biết chính xác field đang là Array hay kiểu từng phần tử, nên diễn đạt mục tiêu rõ ràng và chọn biểu thức phù hợp.

### 9.3. Xuất Extended JSON và so sánh

```javascript
const doc = lab.findOne({ _id: result.insertedId, runId: runId });
print(EJSON.stringify(doc, null, 2, { relaxed: false }));
```

Canonical Extended JSON giữ marker cho Int32/Int64/Date/Decimal128, hữu ích khi đối chiếu kiểu với dữ liệu đọc qua Java. Dù vậy, cần dùng parser EJSON để dựng lại kiểu tương ứng; JSON parser thông thường không hiểu rằng `{"$numberLong":"..."}` đại diện cho Int64.

Sau khi quan sát xong, dọn **duy nhất bản ghi của lần chạy hiện tại**:

```javascript
lab.deleteOne({ _id: result.insertedId, runId: runId });
```

Không dùng `deleteMany({})` hoặc `drop()` trên collection khác nếu chưa xác định rõ dữ liệu của ai.

## 10. Kiểu BSON trong truy vấn, chỉ mục và validator

### 10.1. Đồng nhất kiểu quan trọng hơn cách hiển thị

Giả sử một collection lưu `customerId` vừa có String `"665f..."`, vừa có ObjectId cùng biểu diễn. Truy vấn `{ customerId: ObjectId("...") }` không mặc nhiên khớp với String tương ứng, và điều này không được giải quyết chỉ bằng cách thêm index.

Để có hợp đồng dữ liệu ổn định, nên:

1. Quy định BSON type của mỗi field quan trọng ngay từ thiết kế.
2. Chọn đúng Java type, Spring Data annotation hoặc custom converter tương ứng.
3. Kiểm tra document cũ trước khi chuyển schema/kiểu để tránh cùng field có nhiều representation.
4. Tạo chỉ mục theo query thực tế, quan sát `explain("executionStats")`.
5. Dùng validator khi muốn database từ chối document sai cấu trúc.

### 10.2. JSON Schema validation của MongoDB kiểm tra BSON type

Ví dụ tạo **collection mới dành riêng cho bài tập validator**:

```javascript
db.createCollection("typed_products_lab", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "stock", "price"],
      properties: {
        sku: {
          bsonType: "string",
          description: "sku phải là String"
        },
        stock: {
          bsonType: "int",
          minimum: 0,
          description: "stock phải là Int32 không âm"
        },
        price: {
          bsonType: "decimal",
          description: "price phải là Decimal128"
        }
      }
    }
  }
});
```

Từ đó, ghi đúng kiểu:

```javascript
db.typed_products_lab.insertOne({
  sku: "SKU-01",
  stock: NumberInt(8),
  price: NumberDecimal("199.90")
});
```

Nếu ghi `price: "199.90"` là String hoặc `stock: "8"` là String thì validator từ chối khi validation đang được thực thi (theo cấu hình validation level/action). Một unique index là quy tắc **duy nhất** của giá trị, còn validator kiểm tra **kiểu và cấu trúc**; chúng giải quyết hai yêu cầu khác nhau.

Ví dụ `createCollection` chỉ chạy nếu tên collection chưa tồn tại. Đây là một mẫu thiết kế, không phải yêu cầu tạo validator trên collection dữ liệu thật. Khi dùng Spring Data MongoDB, annotation Java không tự thay thế toàn bộ MongoDB JSON Schema validator; cần quy trình quản lý schema/index riêng theo dự án.

### 10.3. Chẩn đoán bằng aggregation

Để biết một field tiền có đang bị trộn kiểu hay không, có thể phân nhóm theo BSON type:

```javascript
db.catalog_items.aggregate([
  {
    $group: {
      _id: { $type: "$unitPrice" },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
]);
```

Kết quả có thể cho biết collection đang chứa `decimal`, `double`, `string` hoặc `missing`. Đây là bước chẩn đoán trước khi quyết định migration. Không tự động chạy `$toDecimal` trên mọi chuỗi nếu chưa xử lý các giá trị sai định dạng, scale và quy tắc làm tròn.

## 11. Lỗi thường gặp và hướng kiểm tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
| --- | --- | --- |
| Số tiền `0.1 + 0.2` khác `0.3` | Double là số dấu chấm động nhị phân | Dùng số nguyên đơn vị nhỏ nhất hoặc Decimal128/BigDecimal theo hợp đồng tiền tệ |
| Giá trị Long rất lớn bị đổi khi đi qua JSON/JavaScript | JavaScript Number chỉ chính xác số nguyên trong phạm vi an toàn | Dùng NumberLong từ chuỗi, EJSON/codec hiểu Int64 |
| `BigDecimal` lưu thành String | Quy tắc mặc định mapping hoặc converter | Kiểm tra `$type`, dùng `@Field(targetType = FieldType.DECIMAL128)` |
| Truy vấn `_id` không khớp | BSON ObjectId bị đem so với BSON String | Kiểm tra loại thực, chọn `@Id`/`@MongoId` và convert đúng |
| UUID đọc ra khác dự kiến | Subtype/UUID representation không nhất quán | Xác định representation; kiểm tra subtype và byte order |
| Trường ngày giờ lệch 7 giờ | Diễn giải LocalDateTime và múi giờ sai | Lưu Instant UTC; lưu zone riêng nếu cần phục hồi giờ địa phương |
| Mốc thời gian mất phần nanosecond | BSON Date chỉ có mili giây | Chọn độ phân giải dữ liệu phù hợp hoặc thiết kế lưu bổ sung |
| Không phân biệt missing với `null` | Java reference null hoặc truy vấn `{ field: null }` gộp trường hợp | Dùng `$exists`, `$type` và mô hình ba trạng thái rõ ràng |
| Primitive `int` nhận 0 dù field chưa được cung cấp | Default của Java primitive | Dùng `Integer` khi cần phân biệt "không có giá trị" |
| Enum cũ không còn đọc được | Đổi tên hằng enum trong khi DB lưu String name | Dùng mã giá trị ổn định hoặc custom converter và migration |
| Dữ liệu nested/list chuyển đổi lỗi | Loại phần tử BSON không phù hợp với generic type Java | Kiểm tra dữ liệu bằng `$type`, chuẩn hóa schema và converter |
| Phép so sánh hoặc aggregation trả kết quả khó hiểu | Field cùng tên có nhiều loại BSON | Phân nhóm theo `$type`, sửa dữ liệu và validator |

Khi chẩn đoán, hãy bắt đầu từ **document BSON thực tế** bằng `mongosh` hoặc Compass. Sau đó kiểm tra metadata Java, các converter đang chạy và đường ghi thực tế (Spring Data repository/template hay Java Driver trực tiếp). Cùng một JSON từ REST API không chứng minh hai document lưu cùng loại BSON.

## 12. Bài tập thực hành

**Bài 1 — Phân loại kiểu.** Với document có `qty: NumberInt(7)`, `views: NumberLong("9007199254740993")`, `price: NumberDecimal("15.75")`, `createdAt: ISODate(...)`, hãy viết bảng đối chiếu từng BSON type với Java type thích hợp. Giải thích vì sao không nên đọc `views` vào `int`.

**Bài 2 — Tiền và precision.** Tạo entity `Product` có `quantity`, `price`, `createdAt`; chọn một phương án lưu tiền (minor units hoặc Decimal128), nêu rõ currency, scale và quy tắc rounding. Dùng `mongosh` xác nhận `$type` của field `price`.

**Bài 3 — ObjectId và String.** Tạo hai document có `_id` mang cùng ký tự hex nhưng khác loại BSON. Viết hai truy vấn nhận đúng document tương ứng; chọn giữa `@Id String` và `@MongoId String` nếu ứng dụng cần luôn giữ mã dạng chuỗi.

**Bài 4 — Null hay missing.** Tạo ba document lần lượt có `note: null`, thiếu `note` và `note: ""`. Viết ba bộ lọc để nhận đúng từng nhóm; thử ánh xạ vào `String` và mô tả thông tin bị mất nếu chỉ nhìn object Java.

**Bài 5 — Date và zone.** Một khách hàng ở múi giờ Asia/Ho_Chi_Minh đặt lịch lúc 15:00 ngày 20/11/2026. Hãy tính instant UTC tương ứng, lưu dưới BSON Date, rồi giải thích cách tái dựng giờ hiển thị và vì sao phải giữ zone ID khi yêu cầu nghiệp vụ cần nó.

**Bài 6 — UUID.** Ghi một UUID dưới BSON Binary subtype 4 bằng cấu hình driver phù hợp và đọc lại bằng Java `UUID`. So sánh với document khác lưu chính UUID đó dưới BSON String, rồi giải thích vì sao truy vấn không thể xem hai kiểu lưu là tương đương.

**Bài 7 — Phát hiện schema drift.** Trên một collection thử nghiệm, chèn giá `unitPrice` dưới ba dạng `String`, `Double`, `Decimal128`. Dùng aggregation với `$type` để thống kê, đề xuất migration an toàn và validator chặn dữ liệu không đúng kiểu trong tương lai.

### Ghi nhớ

**Kiểu BSON là hợp đồng dữ liệu thực tế của MongoDB.** Java có các kiểu tương ứng nhưng sự chuyển đổi phụ thuộc Spring Data MongoDB, driver, annotation và converter. Hãy chủ động chọn Int32/Int64, Decimal128, Date/Instant, ObjectId và UUID/Binary theo nghiệp vụ; phân biệt missing với null, tránh trộn kiểu trên cùng field và luôn xác nhận bằng `$type` hoặc Extended JSON trước khi kết luận dữ liệu được lưu đúng.
