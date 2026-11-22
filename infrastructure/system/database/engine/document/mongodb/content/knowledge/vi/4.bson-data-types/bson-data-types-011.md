# Đọc ghi Extended JSON mà không làm mất thông tin kiểu BSON

## 1. Vấn đề: JSON nhìn giống BSON nhưng không mang đủ thông tin kiểu

MongoDB lưu document theo định dạng **BSON (Binary JSON)**. BSON biểu diễn các cấu trúc document/array tương tự JSON, nhưng có thêm nhiều kiểu giá trị với ý nghĩa và quy tắc xử lý riêng: **ObjectId**, **Date**, **Int32**, **Int64**, **Double**, **Decimal128**, **Binary**, **Timestamp**, **Regular Expression** và một số kiểu đặc biệt khác.

JSON thông thường chỉ có object, array, string, number, boolean và null. Nó **không có cú pháp chuẩn** để phân biệt số nguyên 32-bit với số nguyên 64-bit, số thực double với Decimal128, hay chuỗi ký tự với ngày giờ BSON.

Giả sử database có document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberInt(12),
  sequence: NumberLong("9007199254740993"),
  unitPrice: NumberDecimal("19.99"),
  createdAt: ISODate("2024-01-01T00:00:00.000Z")
}
~~~

Đây là **cú pháp biểu diễn giá trị trong mongosh**, không phải chuỗi JSON hợp lệ. Nếu ép document thành JSON đơn giản như sau:

~~~json
{
  "_id": "507f1f77bcf86cd799439011",
  "quantity": 12,
  "sequence": 9007199254740993,
  "unitPrice": 19.99,
  "createdAt": "2024-01-01T00:00:00.000Z"
}
~~~

thì dữ liệu trở nên dễ đọc hơn nhưng đánh mất nhiều điều:

- **_id** chỉ còn là string; không có thông tin cho biết nó từng là ObjectId.
- **quantity** là JSON number; không còn nhãn Int32.
- **sequence** là JSON number quá lớn để JavaScript biểu diễn chính xác bằng kiểu Number; khi đi qua một số hệ thống, giá trị có thể bị làm tròn.
- **unitPrice** mất kiểu Decimal128, có thể đi qua phép tính dấu phẩy động gây sai số.
- **createdAt** chỉ còn chuỗi; parser JSON thông thường không tự tạo BSON Date.

Vấn đề này đặc biệt nghiêm trọng ở các luồng **export/import**, truyền dữ liệu giữa Java và JavaScript, lưu file JSON để tái nhập, xử lý sự kiện qua message queue hoặc thực hiện migration.

**MongoDB Extended JSON (EJSON)** giải quyết bài toán bằng những **type wrapper** có tên khóa bắt đầu bằng dấu **$**. Type wrapper làm rõ giá trị nguyên bản khi chuyển giữa BSON và văn bản JSON.

## 2. Extended JSON v2 là gì?

**Extended JSON v2** là quy ước biểu diễn các giá trị BSON dưới dạng văn bản JSON hợp lệ, cho phép công cụ/driver MongoDB tạo lại kiểu tương ứng. Ví dụ:

~~~json
{
  "_id": { "$oid": "507f1f77bcf86cd799439011" },
  "quantity": { "$numberInt": "12" },
  "sequence": { "$numberLong": "9007199254740993" },
  "unitPrice": { "$numberDecimal": "19.99" },
  "createdAt": {
    "$date": { "$numberLong": "1704067200000" }
  }
}
~~~

Từng wrapper có ý nghĩa cụ thể:

- **$oid:** một ObjectId có 12 byte, biểu diễn bằng 24 ký tự hex.
- **$numberInt:** số nguyên có dấu 32-bit.
- **$numberLong:** số nguyên có dấu 64-bit.
- **$numberDecimal:** số thập phân Decimal128.
- **$date:** BSON Date; dạng canonical ở trên chứa epoch milliseconds trong **$numberLong**.

Các chuỗi số bên trong wrapper là chủ ý của định dạng. Chẳng hạn, **"9007199254740993"** được giữ dưới dạng chuỗi để tránh việc JSON parser dùng Number làm tròn nó trước khi tạo Int64.

### 2.1. Hai chế độ được chuẩn hóa

EJSON v2 có hai chế độ chính:

| Chế độ | Mục tiêu | Mức bảo toàn kiểu BSON | Trường hợp sử dụng |
|---|---|---|---|
| **Canonical Extended JSON** | Biểu diễn rõ kiểu của BSON để có thể round-trip. | Cao nhất trong hai chế độ; vẫn có một số ngoại lệ/giới hạn đặc tả. | Trao đổi dữ liệu cần giữ nguyên kiểu, migration, test fixture, kiểm tra kiểu. |
| **Relaxed Extended JSON** | Ngắn, dễ đọc, gần JSON thông thường. | Có thể mất loại số Int32/Int64/Double và mất độ chính xác khi các JSON number đi qua parser không hỗ trợ. | Log/hiển thị, trao đổi API khi schema định nghĩa sẵn các kiểu và chấp nhận chuyển đổi. |

**Canonical** ưu tiên tính trung thực của kiểu. **Relaxed** ưu tiên sự tiện dụng và khả năng đọc. Hai chế độ đều là **JSON hợp lệ về cú pháp**, nhưng chỉ parser có hiểu EJSON mới tái tạo BSON từ những wrapper đặc biệt.

### 2.2. Canonical và relaxed của cùng document

Canonical:

~~~json
{
  "count32": { "$numberInt": "42" },
  "count64": { "$numberLong": "42" },
  "ratio": { "$numberDouble": "2.5" },
  "cost": { "$numberDecimal": "12.50" },
  "createdAt": { "$date": { "$numberLong": "1704067200000" } },
  "_id": { "$oid": "507f1f77bcf86cd799439011" }
}
~~~

Relaxed:

~~~json
{
  "count32": 42,
  "count64": 42,
  "ratio": 2.5,
  "cost": { "$numberDecimal": "12.50" },
  "createdAt": { "$date": "2024-01-01T00:00:00Z" },
  "_id": { "$oid": "507f1f77bcf86cd799439011" }
}
~~~

Ở bản relaxed, **count32** và **count64** đều thành **42**. Từ JSON number 42, một parser không thể tự biết kiểu ban đầu là Int32 hay Int64. Trong khi đó **Decimal128** và **ObjectId** vẫn cần wrapper ở cả hai chế độ.

**Quy tắc thực hành:** nếu yêu cầu là “đọc ghi mà không làm mất thông tin kiểu BSON”, hãy chọn **Canonical EJSON** và dùng **EJSON-aware reader/writer** ở cả hai phía.

## 3. Bảng biểu diễn các kiểu BSON quan trọng

Bảng dưới đây tập trung vào **Extended JSON v2**. Ví dụ được viết thành các giá trị JSON độc lập để thấy rõ wrapper.

| Kiểu BSON | Canonical EJSON | Relaxed EJSON | Điều dễ mất khi chuyển đổi sai |
|---|---|---|---|
| **ObjectId** | **{"$oid":"507f1f77bcf86cd799439011"}** | Giống canonical. | Bị thay thành string 24 ký tự. |
| **Int32** | **{"$numberInt":"42"}** | **42** | Không còn biết đó là số nguyên 32-bit. |
| **Int64** | **{"$numberLong":"42"}** | **42** | Không còn biết đó là số nguyên 64-bit; số lớn có nguy cơ bị làm tròn. |
| **Double** | **{"$numberDouble":"2.5"}** | **2.5** | Không phân biệt chính xác với các loại số khác nếu parser tự suy luận. |
| **Decimal128** | **{"$numberDecimal":"19.99"}** | Giống canonical. | Nếu đổi thành Number có thể mất độ chính xác thập phân. |
| **Date** | **{"$date":{"$numberLong":"1704067200000"}}** | **{"$date":"2024-01-01T00:00:00Z"}** | Nhầm với string nếu bỏ wrapper. |
| **Binary** | **{"$binary":{"base64":"AQIDBA==","subType":"00"}}** | Giống canonical. | Mất byte thực và/hoặc subtype nếu chỉ giữ base64 string. |
| **Timestamp** | **{"$timestamp":{"t":1704067200,"i":1}}** | Giống canonical. | Nhầm với BSON Date hoặc object thông thường. |
| **Regex** | **{"$regularExpression":{"pattern":"^VIP","options":"i"}}** | Giống canonical. | Mất semantics biểu thức chính quy và flags. |
| **MinKey** | **{"$minKey":1}** | Giống canonical. | Không còn kiểu đặc biệt có thứ tự nhỏ nhất trong BSON. |
| **MaxKey** | **{"$maxKey":1}** | Giống canonical. | Không còn kiểu đặc biệt có thứ tự lớn nhất trong BSON. |

Các kiểu như **boolean**, **string**, **null**, array và document thông thường có thể dùng cú pháp JSON tự nhiên. Tuy nhiên, nếu array hoặc document lồng nhau chứa kiểu BSON đặc biệt, wrapper phải được giữ **đệ quy** ở những vị trí đó.

### 3.1. ObjectId khác chuỗi 24 ký tự

~~~json
{
  "mongoId": { "$oid": "507f1f77bcf86cd799439011" },
  "plainText": "507f1f77bcf86cd799439011"
}
~~~

Hai trường trông giống nhau nhưng **mongoId** mang kiểu ObjectId, còn **plainText** mang kiểu string. Nếu Java hoặc MongoDB truy vấn theo **_id** là ObjectId mà ứng dụng gửi vào string, kết quả so khớp có thể khác mong đợi.

### 3.2. Int32, Int64 và Double là ba kiểu khác nhau

~~~json
{
  "a": { "$numberInt": "7" },
  "b": { "$numberLong": "7" },
  "c": { "$numberDouble": "7.0" }
}
~~~

Trong JSON thuần, ba giá trị có thể cùng được xử lý như number. Trong BSON, chúng mang **ba type tag** khác nhau. Điều này liên quan đến schema, mapping Java, kiểm tra kiểu bằng **$type** và trao đổi dữ liệu.

Đặc biệt, JavaScript Number chỉ biểu diễn chính xác **các số nguyên trong khoảng từ -(2^53 - 1) đến +(2^53 - 1)**. Số nguyên 64-bit có thể nằm ngoài khoảng này.

~~~javascript
// Chạy trong môi trường JavaScript:
Number.MAX_SAFE_INTEGER                 // 9007199254740991
Number("9007199254740993")              // có thể thành 9007199254740992
Number.isSafeInteger(9007199254740993)  // false
~~~

Khi chuỗi số đã bị parser làm tròn, việc thêm **$numberLong** ở bước sau **không thể phục hồi chữ số bị mất**. Phải giữ dữ liệu ở dạng canonical ngay từ trước bước parse gây mất chính xác.

### 3.3. Decimal128 dành cho giá trị thập phân cần độ chính xác

~~~json
{
  "price": { "$numberDecimal": "19.99" },
  "interestRate": { "$numberDecimal": "0.012500" }
}
~~~

**Decimal128** thường có ích cho giá, tiền tệ, số đo và số thập phân có yêu cầu chính xác hơn số thực nhị phân. Đừng chuyển nó sang double chỉ để JSON ngắn hơn. Ứng dụng Java nên dùng loại tương thích như **Decimal128** hoặc chuyển đổi có kiểm soát sang **BigDecimal** theo hợp đồng dữ liệu.

### 3.4. Date là một instant; string có thể chứa nhiều biểu diễn khác

~~~json
{
  "asDate": { "$date": "2024-01-01T00:00:00Z" },
  "asString": "2024-01-01T00:00:00Z"
}
~~~

**asDate** được EJSON parser chuyển thành BSON Date, còn **asString** vẫn là string. BSON Date lưu **số mili giây tính từ Unix epoch**, không lưu nguyên múi giờ người dùng đã nhập. Hai timestamp với offset khác nhau nhưng cùng instant sẽ được lưu thành cùng thời điểm; **thông tin múi giờ ban đầu** cần trường riêng nếu nghiệp vụ phải giữ nó.

Canonical Date dùng:

~~~json
{ "$date": { "$numberLong": "1704067200000" } }
~~~

Relaxed Date thường dùng ISO-8601 khi thời điểm nằm trong khoảng được hỗ trợ. Với thời điểm nằm ngoài khoảng biểu diễn relaxed tương ứng (chẳng hạn trước năm 1970), exporter có thể dùng lại biểu diễn epoch milliseconds dạng canonical.

### 3.5. Binary phải giữ cả bytes lẫn subtype

~~~json
{
  "rawData": {
    "$binary": {
      "base64": "AQIDBA==",
      "subType": "00"
    }
  },
  "uuidAsBinary": {
    "$binary": {
      "base64": "OyQRAeK7QlWMr0E2xWapYg==",
      "subType": "04"
    }
  }
}
~~~

Base64 là cách biểu diễn **bytes**, không phải text gốc. Trường **subType** là một phần thông tin kiểu của BSON binary:

- **00** thường dùng cho generic binary.
- **04** dùng cho UUID theo định dạng chuẩn tương ứng.

EJSON còn có biểu diễn UUID tiện dụng như:

~~~json
{ "$uuid": "3b241101-e2bb-4255-8caf-4136c566a962" }
~~~

Parser EJSON hỗ trợ có thể chuyển wrapper này thành **BSON binary subtype 04**. Đừng tự thay mọi binary thành UUID hoặc đổi subtype 03/04 khi chưa hiểu representation cũ và cấu hình UUID của driver; **cùng 16 byte** chưa đủ để xác định kiểu/semantics UUID như mong muốn.

### 3.6. Timestamp không phải Date

~~~json
{
  "createdAt": { "$date": "2024-01-01T00:00:00Z" },
  "opTime": { "$timestamp": { "t": 1704067200, "i": 1 } }
}
~~~

**Date** là mili giây từ epoch. **BSON Timestamp** gồm một phần thời gian (**t**) và bộ đếm tăng (**i**) mang semantics riêng, thường gặp trong các ngữ cảnh nội bộ như replication/oplog. Đừng tự đổi **Timestamp** thành Date nếu ứng dụng cần bảo toàn loại BSON.

### 3.7. Double với NaN và vô cực

JSON chuẩn không có literal **NaN**, **Infinity** hoặc **-Infinity**. Extended JSON dùng:

~~~json
{
  "notANumber": { "$numberDouble": "NaN" },
  "positiveInfinity": { "$numberDouble": "Infinity" },
  "negativeInfinity": { "$numberDouble": "-Infinity" }
}
~~~

Ngay trong relaxed mode, những giá trị phi hữu hạn vẫn cần wrapper. Ngoài ra, với một số kiểu dữ liệu số thực, yêu cầu bảo toàn **type** không tự đồng nghĩa với yêu cầu bảo toàn từng bit của mọi biểu diễn phần cứng bất thường; khi cần byte-for-byte fidelity, hãy làm việc trực tiếp với BSON và đặc tả tương ứng.

## 4. Một document Canonical EJSON hoàn chỉnh

Ví dụ này có thể dùng làm payload tập tin để chuyển qua hệ thống khác:

~~~json
{
  "_id": { "$oid": "507f1f77bcf86cd799439011" },
  "orderCode": "ORD-0007",
  "tenantId": "TENANT-A",
  "quantity": { "$numberInt": "2" },
  "sequence": { "$numberLong": "9007199254740993" },
  "unitPrice": { "$numberDecimal": "129.9900" },
  "discountRate": { "$numberDouble": "0.125" },
  "paid": false,
  "createdAt": {
    "$date": { "$numberLong": "1704067200000" }
  },
  "receiptBytes": {
    "$binary": { "base64": "AQIDBA==", "subType": "00" }
  },
  "tags": ["new", "priority"],
  "warehouseStock": [
    { "warehouse": "HN", "units": { "$numberInt": "12" } },
    { "warehouse": "HCM", "units": { "$numberInt": "8" } }
  ],
  "fulfillment": null
}
~~~

Khi parse bằng EJSON-aware parser, ta có:

| Trường | Kiểu BSON muốn nhận lại |
|---|---|
| **_id** | ObjectId |
| **orderCode**, **tenantId**, **tags[]** | String |
| **quantity**, **warehouseStock[].units** | Int32 |
| **sequence** | Int64 |
| **unitPrice** | Decimal128 |
| **discountRate** | Double |
| **paid** | Boolean |
| **createdAt** | Date |
| **receiptBytes** | Binary subtype 00 |
| **fulfillment** | Null |

Một reader không hiểu EJSON sẽ xem **{"$numberLong":"9007199254740993"}** là object bình thường chứa một key tên **$numberLong**, không phải Int64. Vì vậy **chỉ đúng cấu trúc JSON chưa đủ; bước giải mã phải đúng chuẩn Extended JSON**.

## 5. Đọc và ghi EJSON trong mongosh

**mongosh** cung cấp các hàm **EJSON** để serialize/deserialize giá trị có kiểu BSON:

| Hàm | Vai trò |
|---|---|
| **EJSON.stringify(value, ..., options)** | Trả về **chuỗi JSON** được encode theo EJSON. |
| **EJSON.parse(text, options)** | Đọc **chuỗi EJSON** và phục hồi các giá trị BSON tương ứng. |
| **EJSON.serialize(value, options)** | Trả về **đối tượng JavaScript** có các type wrapper EJSON. |
| **EJSON.deserialize(value, options)** | Đọc đối tượng EJSON đã được serialize và phục hồi giá trị BSON. |

Điểm khác: **stringify/parse** làm việc với **văn bản**; **serialize/deserialize** làm việc với **giá trị đối tượng**. Cả hai cặp đều cần người dùng lựa chọn đúng chế độ.

### 5.1. Tạo document có nhiều kiểu BSON

Trong mongosh, chạy:

~~~javascript
use ejson_lab

const original = {
  _id: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberInt(12),
  sequence: NumberLong("9007199254740993"),
  unitPrice: NumberDecimal("19.99"),
  discountRate: 0.125,
  createdAt: ISODate("2024-01-01T00:00:00Z"),
  payload: BinData(0, "AQIDBA==")
};
~~~

Các hàm **ObjectId**, **NumberInt**, **NumberLong**, **NumberDecimal**, **ISODate** và **BinData** ở đây là **constructor/helper của mongosh**. Đừng dán chính xác đoạn này làm nội dung file JSON rồi yêu cầu parser JSON thuần đọc nó.

### 5.2. Ghi ra Canonical EJSON và đọc lại

~~~javascript
const canonicalText = EJSON.stringify(
  original,
  null,
  2,
  { relaxed: false }
);

print(canonicalText);

const restored = EJSON.parse(canonicalText);

// Lưu document đã phục hồi vào MongoDB.
db.samples.insertOne(restored);
~~~

Tham số **relaxed: false** yêu cầu Canonical EJSON. **EJSON.parse** hiểu các wrapper để tạo lại BSON values; khác với **JSON.parse**, vốn chỉ cho ra object/number/string của JavaScript.

Nếu muốn xử lý dưới dạng đối tượng EJSON thay cho chuỗi:

~~~javascript
const ejsonObject = EJSON.serialize(original, { relaxed: false });
const bsonValues = EJSON.deserialize(ejsonObject);

db.samples.insertOne(bsonValues);
~~~

Khi thực hành nhiều lần, hai lệnh **insertOne** trong ví dụ có cùng **_id** sẽ gây **duplicate key** nếu chạy liên tiếp vào cùng collection. Có thể chọn một cách ghi, đổi **_id** hoặc dùng collection khác để thử từng cách.

### 5.3. Kiểm tra kiểu sau khi insert

Dùng **$type** trong aggregation để quan sát kiểu lưu trữ, thay vì nhìn console và suy đoán:

~~~javascript
db.samples.aggregate([
  {
    $match: { _id: ObjectId("507f1f77bcf86cd799439011") }
  },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      quantityType: { $type: "$quantity" },
      sequenceType: { $type: "$sequence" },
      priceType: { $type: "$unitPrice" },
      createdType: { $type: "$createdAt" },
      payloadType: { $type: "$payload" }
    }
  }
]);
~~~

Kỳ vọng theo kiểu:

~~~javascript
{
  idType: "objectId",
  quantityType: "int",
  sequenceType: "long",
  priceType: "decimal",
  createdType: "date",
  payloadType: "binData"
}
~~~

Để kiểm tra **giá trị** Int64, cũng nên sử dụng constructor/driver hỗ trợ số nguyên 64-bit; đừng chuyển nó sang JavaScript Number trước khi so sánh.

### 5.4. Điều gì xảy ra khi dùng JSON.stringify?

~~~javascript
const nativeJson = JSON.stringify(original);
const nativeCopy = JSON.parse(nativeJson);

print(nativeJson);
// nativeCopy chỉ là các giá trị JSON thông thường.
~~~

Chuỗi JSON thuần không có hợp đồng bắt buộc về việc giữ **ObjectId**, **Date**, **Decimal128** hoặc **Int64**. Một số BSON value có thể cung cấp phương thức **toJSON** riêng, nhưng kết quả không tương đương với Canonical EJSON. Với JavaScript Number vượt ngưỡng an toàn, sai số có thể xảy ra trước cả bước stringify.

**Không dùng JSON.stringify/JSON.parse làm vòng chuyển đổi BSON -> JSON -> BSON yêu cầu bảo toàn kiểu.**

## 6. Đọc và ghi Canonical EJSON bằng MongoDB Java Driver

Trong Java, MongoDB Java driver cung cấp các lớp như **Document**, **BsonDocument**, **BsonValue** và **JsonWriterSettings**. Khi phải bảo toàn chính xác kiểu BSON ở biên I/O, **BsonDocument** là lựa chọn rõ ràng vì nó lưu từng giá trị dưới dạng một kiểu **BsonValue** cụ thể.

### 6.1. Parse Canonical EJSON thành BsonDocument

Ví dụ Java dùng thư viện **org.mongodb:bson** hoặc dependency transitively từ MongoDB Java Sync Driver:

~~~java
import org.bson.BsonDocument;
import org.bson.json.JsonMode;
import org.bson.json.JsonWriterSettings;

public class EjsonRoundTripExample {
    public static void main(String[] args) {
        String canonicalJson = """
            {
              "_id": { "$oid": "507f1f77bcf86cd799439011" },
              "quantity": { "$numberInt": "12" },
              "sequence": { "$numberLong": "9007199254740993" },
              "unitPrice": { "$numberDecimal": "19.99" },
              "createdAt": {
                "$date": { "$numberLong": "1704067200000" }
              }
            }
            """;

        // EJSON-aware parser: phục hồi các kiểu BSON gốc.
        BsonDocument document = BsonDocument.parse(canonicalJson);

        System.out.println(document.get("_id").getBsonType());
        System.out.println(document.get("quantity").getBsonType());
        System.out.println(document.get("sequence").getBsonType());
        System.out.println(document.get("unitPrice").getBsonType());
        System.out.println(document.get("createdAt").getBsonType());

        // Đọc một Int64 dưới dạng long của Java, không qua double.
        long sequence = document.getInt64("sequence").getValue();
        System.out.println(sequence); // 9007199254740993

        JsonWriterSettings canonical = JsonWriterSettings.builder()
                .outputMode(JsonMode.EXTENDED)
                .build();

        // JsonMode.EXTENDED tương ứng Canonical EJSON v2.
        String serialized = document.toJson(canonical);
        BsonDocument restored = BsonDocument.parse(serialized);

        System.out.println(document.equals(restored)); // true với ví dụ này
    }
}
~~~

**BsonDocument.parse** hiểu các type wrapper của EJSON. **JsonMode.EXTENDED** tạo EJSON theo chế độ canonical; tên enum trong Java driver là **EXTENDED**, không phải **CANONICAL**. Việc dùng **BsonDocument** giúp code không vô tình đưa Int64 qua Number/Double của JavaScript.

### 6.2. Relaxed EJSON trong Java

~~~java
JsonWriterSettings relaxed = JsonWriterSettings.builder()
        .outputMode(JsonMode.RELAXED)
        .build();

String humanReadable = document.toJson(relaxed);
System.out.println(humanReadable);
~~~

Kết quả ngắn hơn, nhưng số nguyên Int32/Int64 và số thực Double có thể mất định danh kiểu khi được parse lại. Chỉ chọn **RELAXED** cho luồng mà schema/application chủ động chấp nhận điều đó.

### 6.3. Document khác BsonDocument ở đâu?

~~~java
import org.bson.Document;

Document doc = Document.parse(canonicalJson);
System.out.println(doc.get("_id").getClass().getName());
System.out.println(doc.get("sequence").getClass().getName());
~~~

**Document.parse** cũng hiểu Extended JSON nhưng chuyển về hệ giá trị Java như **ObjectId**, **Long**, **Date**, **Decimal128**. Trong khi đó **BsonDocument** duy trì cấu trúc typed BSON rõ ở từng field. Với ứng dụng Spring Data MongoDB hoặc POJO mapping, converter và kiểu field Java cũng tham gia quyết định dữ liệu được lưu/đọc; việc dùng Canonical EJSON chỉ bảo đảm tốt đường chuyển đổi khi các lớp trung gian không ép kiểu sai.

### 6.4. Lưu ý khi đưa dữ liệu vào DTO/POJO

Giả sử JSON EJSON có **{"$numberLong":"9007199254740993"}**, nhưng DTO Java lại khai báo field kiểu **double**. Hệ thống có thể chuyển đổi sai khi bind DTO, bất kể văn bản đầu vào đúng canonical. Nên dùng:

- **long/Long** cho Int64 trong giới hạn Java signed 64-bit.
- **int/Integer** cho Int32.
- **BigDecimal/Decimal128** khi nghiệp vụ cần số thập phân chính xác, với converter phù hợp.
- **ObjectId** hoặc converter có kiểm soát cho BSON ObjectId.
- **Instant/Date** với quy ước UTC và độ chính xác mili giây cho BSON Date.
- **byte[]/Binary** kèm subtype nếu nghiệp vụ cần phân biệt các loại binary.

EJSON giúp **mang thông tin kiểu qua ranh giới văn bản**, nhưng việc khôi phục chính xác còn phụ thuộc lớp đọc, DTO, codec và converter ở ứng dụng.

## 7. Export và import bằng MongoDB Database Tools

Hai công cụ dành cho dữ liệu dạng JSON là **mongoexport** và **mongoimport**. Chúng dùng Extended JSON v2 trong các phiên bản Database Tools hiện đại.

### 7.1. Export mặc định thường ở relaxed mode

Ví dụ:

~~~bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017/shop" \
  --collection=orders \
  --out=orders-relaxed.jsonl
~~~

Theo mặc định, **mongoexport** xuất Extended JSON v2 ở **relaxed mode**. Kiểu số cụ thể có thể không được giữ đầy đủ khi file được tái nhập, đặc biệt nếu có thêm một bước xử lý qua JSON parser khác.

### 7.2. Chọn canonical để giữ kiểu khi chuyển dữ liệu

~~~bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017/shop" \
  --collection=orders \
  --jsonFormat=canonical \
  --out=orders-canonical.jsonl
~~~

Tham số **--jsonFormat=canonical** là phần quyết định chế độ. Tên file **.jsonl** được dùng để nhắc rằng đầu ra mặc định là **mỗi document một dòng JSON** (JSON Lines); không cần toàn bộ file là một array JSON.

Lệnh nhiều dòng minh họa cú pháp shell Linux/macOS. Trong PowerShell, có thể viết thành một dòng hoặc dùng cú pháp xuống dòng thích hợp:

~~~powershell
mongoexport --uri="mongodb://127.0.0.1:27017/shop" --collection=orders --jsonFormat=canonical --out=orders-canonical.jsonl
~~~

Kết quả là văn bản có wrapper cho các kiểu đặc biệt. Một dòng có thể trông như:

~~~json
{"_id":{"$oid":"507f1f77bcf86cd799439011"},"quantity":{"$numberInt":"2"},"sequence":{"$numberLong":"9007199254740993"},"createdAt":{"$date":{"$numberLong":"1704067200000"}}}
~~~

### 7.3. Import vào database/collection đích

~~~bash
mongoimport \
  --uri="mongodb://127.0.0.1:27017/shop_copy" \
  --collection=orders \
  --file=orders-canonical.jsonl \
  --mode=insert \
  --stopOnError
~~~

**mongoimport** nhận Extended JSON v2 canonical hoặc relaxed trong cấu hình mặc định phù hợp. Nó giải mã các wrapper thành BSON khi ghi. **--stopOnError** giúp quá trình import dừng khi gặp lỗi thay vì tiếp tục qua một số loại lỗi dữ liệu.

Ở đây import vào **shop_copy** để tránh đè/chèn trùng document trong database nguồn. Nếu collection đích đã chứa cùng **_id**, import có thể gặp lỗi duplicate key; hãy lập kế hoạch migration rõ ràng trước khi chạy trong môi trường thật.

### 7.4. File JSON array khác JSON Lines

Theo mặc định **mongoexport** xuất mỗi document trên một dòng. Nếu muốn xuất thành một JSON array dùng **--jsonArray**, công cụ import tương ứng cũng phải nhận **--jsonArray**; đồng thời chú ý giới hạn kích thước của chế độ này.

~~~bash
mongoexport --uri="mongodb://127.0.0.1:27017/shop" --collection=orders --jsonFormat=canonical --jsonArray --out=orders-array.json
mongoimport --uri="mongodb://127.0.0.1:27017/shop_copy" --collection=orders --jsonArray --file=orders-array.json
~~~

Đừng trộn cách đọc line-delimited với một file array, hoặc ngược lại, nếu không thiết lập parser phù hợp.

### 7.5. Export/import JSON không phải backup đầy đủ

**mongoexport/mongoimport** hữu ích cho di chuyển dữ liệu ở dạng văn bản nhưng **không thay thế mongodump/mongorestore** cho yêu cầu backup/restore đầy đủ. Export JSON không tự lưu mọi index, collection options, users/roles, metadata, điều kiện nhất quán của toàn database và các yếu tố cần thiết của một bản backup trong lúc hệ thống đang có ghi.

Khi cần sao lưu MongoDB có tính phục hồi, cân nhắc **mongodump/mongorestore**, công cụ backup tương thích với topology hoặc giải pháp backup của dịch vụ vận hành; không chọn file JSON chỉ vì nó dễ mở bằng trình soạn thảo.

## 8. Thực hành round-trip và xác minh kiểu sau import

Một quy trình kiểm tra phù hợp ở môi trường lab:

1. Chuẩn bị một collection chứa nhiều BSON types đặc trưng.
2. Xuất bằng **--jsonFormat=canonical**.
3. Đọc bằng EJSON parser, tránh xử lý intermediate qua **JSON.parse** như một bản sao kiểu BSON.
4. Import vào collection khác.
5. So sánh **giá trị và kiểu BSON**, đặc biệt Int32/Int64/Double/Decimal128/Date/Binary.

### 8.1. Tạo dữ liệu mẫu

Trong mongosh:

~~~javascript
use ejson_lab

db.type_samples.insertOne({
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tinyCount: NumberInt(15),
  hugeCount: NumberLong("9007199254740993"),
  exchangeRate: NumberDecimal("1.234567890123456789"),
  measurement: 12.5,
  activeSince: ISODate("2024-01-01T00:00:00Z"),
  blob: BinData(0, "AQIDBA=="),
  tags: ["canonical", "bson"]
});
~~~

### 8.2. Xuất và nhập

~~~bash
mongoexport --uri="mongodb://127.0.0.1:27017/ejson_lab" --collection=type_samples --jsonFormat=canonical --out=type_samples.jsonl
mongoimport --uri="mongodb://127.0.0.1:27017/ejson_lab" --collection=type_samples_copy --file=type_samples.jsonl --stopOnError
~~~

### 8.3. So sánh kiểu bằng aggregation

~~~javascript
const inspectTypes = (collectionName) =>
  db.getCollection(collectionName).aggregate([
    {
      $project: {
        _id: 0,
        tinyCount: { $type: "$tinyCount" },
        hugeCount: { $type: "$hugeCount" },
        exchangeRate: { $type: "$exchangeRate" },
        measurement: { $type: "$measurement" },
        activeSince: { $type: "$activeSince" },
        blob: { $type: "$blob" }
      }
    }
  ]).toArray();

printjson(inspectTypes("type_samples"));
printjson(inspectTypes("type_samples_copy"));
~~~

Trong trường hợp ví dụ được nhập đúng, cả hai kết quả đều chứa các tên kiểu:

~~~json
{
  "tinyCount": "int",
  "hugeCount": "long",
  "exchangeRate": "decimal",
  "measurement": "double",
  "activeSince": "date",
  "blob": "binData"
}
~~~

Việc **$type** giống nhau là một kiểm tra có ích nhưng chưa đủ để khẳng định mọi giá trị bằng nhau. Cần kiểm tra thêm Int64 lớn, Decimal128, **binary subtype**, giá trị thời gian mili giây và những field lồng nhau.

### 8.4. So sánh trên đường Java

Khi cần kiểm tra từng document được parse từ chuỗi canonical, có thể so sánh **BsonDocument** trước/sau serialize:

~~~java
BsonDocument before = BsonDocument.parse(canonicalJson);

JsonWriterSettings canonical = JsonWriterSettings.builder()
        .outputMode(JsonMode.EXTENDED)
        .build();

BsonDocument after = BsonDocument.parse(before.toJson(canonical));

if (!before.equals(after)) {
    throw new IllegalStateException("EJSON round-trip changed BSON values");
}
~~~

Đây là phép so sánh giá trị BSON trong Java đối với dữ liệu được hỗ trợ, **không phải cam kết mọi biểu diễn bit-level đặc biệt đều có thể tái tạo từng byte qua EJSON**. Nếu một workflow đòi hỏi byte-for-byte fidelity, nên dùng BSON binary với codec và version được kiểm soát.

## 9. Các lỗi hay gặp khi đọc/ghi EJSON

### 9.1. Dùng JSON.parse rồi nghĩ đã nhận ObjectId

~~~javascript
const text = '{"_id":{"$oid":"507f1f77bcf86cd799439011"}}';

const ordinary = JSON.parse(text);
const bsonAware = EJSON.parse(text);

printjson(ordinary);
printjson(bsonAware);
~~~

**ordinary._id** vẫn là object có khóa **$oid**; **bsonAware._id** là giá trị BSON ObjectId. Khi cần đưa dữ liệu từ file EJSON vào MongoDB, phải đi qua đúng reader.

### 9.2. Đổi ObjectId thành string rồi tìm kiếm bằng string

~~~javascript
// Nếu _id lưu bằng BSON ObjectId:
db.type_samples.findOne({
  _id: ObjectId("507f1f77bcf86cd799439012")
});

// Chuỗi văn bản có nội dung giống nhau nhưng thuộc kiểu BSON khác:
db.type_samples.findOne({
  _id: "507f1f77bcf86cd799439012"
});
~~~

Kết quả có thể khác nhau. MongoDB có quy tắc so sánh kiểu và giá trị; không giả định ứng dụng tự ép string thành ObjectId.

### 9.3. Đổi Int64 lớn thành JavaScript Number

~~~javascript
const unsafeNumber = 9007199254740993;
const exactLong = NumberLong("9007199254740993");

// unsafeNumber có thể đã bị làm tròn khi tạo Number.
// exactLong được tạo từ chuỗi để giữ giá trị Int64.
~~~

Không sửa được thông tin đã mất chỉ bằng cách gọi **NumberLong(unsafeNumber)**. Hãy giữ giá trị thành chuỗi trong **$numberLong** hoặc sử dụng BSON Long và API hỗ trợ.

### 9.4. Coi Decimal128 như Double

~~~javascript
db.prices.insertOne({
  code: "P-1",
  precise: NumberDecimal("0.1"),
  approximate: 0.1
});
~~~

Hai trường có ý nghĩa khác nhau về kiểu và biểu diễn số. Với nghiệp vụ tài chính, tránh làm phép tính Decimal128 qua các biến **double/Number** nếu hợp đồng yêu cầu decimal chính xác.

### 9.5. Bỏ wrapper $date vì “đã có ISO string”

~~~json
{
  "wrongForBsonDate": "2024-01-01T00:00:00Z",
  "bsonDate": { "$date": "2024-01-01T00:00:00Z" }
}
~~~

String ngày giờ có thể phù hợp một **public REST API** nếu schema định nghĩa việc convert sang Date. Nhưng nó **không phải** Canonical EJSON bảo toàn kiểu BSON ở mức văn bản.

### 9.6. Chỉ giữ base64 mà bỏ subtype

~~~json
{
  "rawString": "AQIDBA==",
  "binaryValue": {
    "$binary": { "base64": "AQIDBA==", "subType": "00" }
  }
}
~~~

Không phải mọi base64 string đều mang nghĩa BSON binary. Subtype còn phân biệt các loại binary, đặc biệt trong tình huống UUID.

### 9.7. Dùng cú pháp của mongosh thay cho JSON hợp lệ

~~~javascript
// Cú pháp cho mongosh hoặc một số biểu diễn shell:
{ _id: ObjectId("507f1f77bcf86cd799439011") }
~~~

~~~json
{
  "_id": { "$oid": "507f1f77bcf86cd799439011" }
}
~~~

Chỉ biểu diễn thứ hai là JSON có thể gửi qua API hoặc lưu thành file chuẩn mà parser JSON thông thường đọc được. MongoDB Java driver có thể có **Shell JSON mode**, nhưng dạng đó không thay thế Canonical EJSON v2 khi giao tiếp với parser JSON chung.

### 9.8. Trộn Extended JSON v1 với v2

MongoDB từng dùng **Legacy Extended JSON v1** với một số wrapper khác, đặc biệt là ngày giờ, binary và regex. Ví dụ cũ có thể dùng biểu diễn **$binary/$type** hoặc **$regex/$options**, khác wrapper tương ứng trong v2.

Các MongoDB Database Tools hiện đại dùng EJSON v2. **mongoimport** có tùy chọn **--legacy** cho dữ liệu v1 nếu cần chuyển dữ liệu cũ; không nên tự áp dụng tùy chọn này với file EJSON v2.

### 9.9. Kết hợp thông tin kiểu với dữ liệu không đáng tin cậy

EJSON parser có thể chuyển các wrapper đặc biệt thành BSON values. Nếu ứng dụng nhận JSON từ người dùng rồi đưa trực tiếp object đã parse làm **MongoDB query filter/update**, kẻ tấn công có thể chèn toán tử truy vấn hoặc field bất ngờ làm đổi semantics.

Ví dụ một filter nhập vào không được kiểm soát:

~~~json
{
  "status": { "$ne": "CANCELLED" }
}
~~~

Điều này không liên quan trực tiếp đến mất type fidelity, nhưng nhấn mạnh rằng **khả năng parse đúng kiểu không đồng nghĩa dữ liệu đầu vào an toàn để thực thi dưới dạng query**. Hãy dùng DTO/schema được cho phép, tự dựng filter từ field hợp lệ và kiểm soát quyền truy cập.

## 10. Thiết kế hợp đồng dữ liệu ở ranh giới ứng dụng

Không phải mọi HTTP API đều cần phơi bày Canonical EJSON. Hãy chọn định dạng dựa trên mục tiêu:

| Nhu cầu | Biểu diễn khuyến nghị | Lưu ý |
|---|---|---|
| **Round-trip MongoDB ↔ file JSON ↔ MongoDB** | Canonical EJSON v2. | Cả writer và reader phải hỗ trợ EJSON. |
| **ETL có bảo toàn BSON types** | Canonical EJSON hoặc BSON binary. | Tránh intermediate ép number sang double. |
| **Java ↔ Node.js với Int64 lớn** | Canonical **$numberLong** hoặc hợp đồng truyền string/Long rõ ràng. | Không đi qua JavaScript Number. |
| **API public trả ngày giờ cho client** | ISO-8601 string nếu contract xác định đó là Date/instant. | Không kỳ vọng JSON.parse tự tạo Date. |
| **Hiển thị log/document cho con người** | Relaxed EJSON nếu chấp nhận mất metadata kiểu số. | Không dùng log này làm source of truth để import. |
| **Backup/restore database** | Công cụ backup có hỗ trợ MongoDB topology. | mongoexport JSON không thay thế backup đầy đủ. |

### 10.1. Phân biệt “chuyển kiểu có chủ đích” và “mất kiểu ngoài ý muốn”

Một API có thể cố ý trả:

~~~json
{
  "id": "507f1f77bcf86cd799439011",
  "createdAt": "2024-01-01T00:00:00Z",
  "price": "19.99"
}
~~~

Đây là **DTO contract hợp lệ** nếu tài liệu API quy định các field là ObjectId string, ISO timestamp và decimal string rồi backend chuyển đổi có kiểm soát. Nhưng đây **không phải EJSON round-trip**. Nó yêu cầu schema và business rules của từng field mới khôi phục được ý nghĩa.

Nếu mục tiêu là trao đổi BSON trung thực, sử dụng:

~~~json
{
  "id": { "$oid": "507f1f77bcf86cd799439011" },
  "createdAt": { "$date": { "$numberLong": "1704067200000" } },
  "price": { "$numberDecimal": "19.99" }
}
~~~

Không cần ép mọi consumer phải hiểu EJSON nếu API có thể công bố rõ và kiểm soát quy tắc chuyển đổi. Vấn đề là **đừng nhầm một DTO dễ đọc với bản sao có thể khôi phục chính xác mọi BSON type**.

### 10.2. Lưu ý với các bước trung gian

Trong hệ thống thực tế, dữ liệu có thể đi qua:

~~~text
MongoDB BSON
   |
   v
MongoDB Driver
   |
   v
Canonical EJSON writer
   |
   v
File / message / HTTP payload
   |
   v
EJSON-aware parser
   |
   v
BSON values / typed DTO
   |
   v
MongoDB destination
~~~

Nếu ở giữa có một bước:

~~~text
Canonical EJSON -> JSON.parse -> tự bóc wrapper -> Number/Date/string
~~~

thì fidelity chỉ còn như logic bóc wrapper đó. Một hệ thống dùng **JavaScript**, **Python**, **Java**, **Go** hoặc một data platform có thể parse JSON number và ngày giờ khác nhau; vì vậy đường dữ liệu phải định nghĩa rõ parser, kiểu sau parse và phép mapping.

### 10.3. Cần quan tâm metadata ngoài document

Đọc ghi EJSON bảo toàn **kiểu của các field trong document** ở mức được hỗ trợ; nó không tự bảo toàn **index definition**, **collection validation**, **collation**, **TTL policy**, **shard key**, users/roles hoặc transaction snapshot. Những nội dung này thuộc quy trình migration/backup/database administration.

## 11. Khi nào nên dùng BSON binary thay vì EJSON?

Canonical EJSON được thiết kế cho văn bản dễ trao đổi và phần lớn trường hợp cần bảo toàn type. Tuy nhiên, **BSON binary** phù hợp hơn khi:

- Cần trao đổi/backup có yêu cầu giữ đúng bản ghi BSON binary hoặc theo tiêu chuẩn tương thích chặt chẽ.
- Dữ liệu nhiều, muốn tránh overhead wrapper text và base64.
- Hệ thống dùng driver MongoDB ở hai đầu, không có nhu cầu người đọc trực tiếp file JSON.
- Có yêu cầu bảo toàn các góc cạnh mà EJSON canonical cũng không cam kết giữ nguyên biểu diễn bit-for-bit.

Ngược lại, Canonical EJSON hữu ích khi phải đi qua hệ thống chỉ chấp nhận JSON nhưng vẫn muốn giữ type tag để có thể tái tạo BSON ở nơi nhận.

## 12. Tình huống thực tế

### 12.1. Khôi phục số thứ tự lớn sau khi truyền qua JavaScript

Một hệ thống Java ghi sequence **9007199254740993** dưới kiểu BSON Int64. Gateway Node.js đọc từ MongoDB, gọi **JSON.stringify** theo cách tự chuyển Long thành number, rồi gửi đến consumer. Consumer nhận **9007199254740992** do vượt giới hạn an toàn của JavaScript Number.

Cách bảo vệ: giữ **BSON Long** trong driver, xuất **{"$numberLong":"9007199254740993"}** hoặc dùng hợp đồng decimal string/BigInt được khai báo rõ; consumer phục hồi bằng EJSON parser hoặc thư viện Long tương ứng.

### 12.2. Đồng bộ dữ liệu đơn hàng nhưng giá bị sai số

Ứng dụng A dùng Decimal128 để lưu giá; ứng dụng B đọc file relaxed hoặc JSON tùy biến rồi đổi giá thành double trước khi tính. Dữ liệu hiển thị có thể trông tương đương nhưng phép tính làm tròn hoặc cộng dồn có thể lệch.

Cách bảo vệ: dùng **$numberDecimal** trong EJSON và mapping Decimal128/BigDecimal đúng ở phía nhận; không chuyển qua số thực nhị phân nếu mục tiêu là tính toán decimal chính xác.

### 12.3. Import lại bị sai kiểu _id

Một script export biến ObjectId thành chuỗi và bỏ wrapper. Khi import, collection mới có **_id kiểu string**. Các truy vấn từ Java driver dùng ObjectId không còn tìm thấy document dù cùng 24 ký tự.

Cách bảo vệ: dùng Canonical EJSON với **$oid**; kiểm tra **$type** sau import.

### 12.4. Log hiển thị date nhưng dữ liệu nhập lại thành string

Ứng dụng ghi log **"createdAt":"2024-01-01T00:00:00Z"** rồi tái sử dụng log làm dữ liệu import. Parser chỉ nhận string, khiến các phép query Date và TTL dựa trên kiểu Date không hoạt động như dự kiến.

Cách bảo vệ: nếu log dự kiến tái sử dụng làm dữ liệu, xuất Canonical EJSON hoặc dùng schema chuyển đổi ngày giờ được kiểm soát; log hiển thị không mặc nhiên là nguồn dữ liệu chuẩn.

## 13. Câu hỏi tự kiểm tra

1. Tại sao JSON number **42** không đủ để phân biệt BSON Int32, Int64 và Double?
2. Vì sao chuyển Int64 **9007199254740993** sang JavaScript Number là rủi ro và **$numberLong** giải quyết vấn đề ở điểm nào?
3. Điểm khác nhau giữa **{"$date":"2024-01-01T00:00:00Z"}** và **"2024-01-01T00:00:00Z"** là gì?
4. **JSON.parse** và **EJSON.parse** khác nhau thế nào khi gặp **$oid**, **$numberDecimal**?
5. Trong MongoDB Java driver, **JsonMode.EXTENDED** và **JsonMode.RELAXED** được dùng cho mục đích gì?
6. Cần tham số nào để **mongoexport** phát sinh Canonical EJSON thay vì relaxed?
7. Tại sao cần giữ **subType** của BSON Binary dù đã có Base64?
8. Vì sao export document kiểu EJSON vẫn chưa đủ để khẳng định đã có bản backup database nhất quán?
9. Khi dữ liệu bị đổi từ ObjectId thành string, làm thế nào kiểm tra được bằng MongoDB aggregation?
10. Một REST API dùng ISO string và decimal string có nhất thiết sai không? Hãy phân biệt DTO contract với round-trip BSON.

## 14. Tóm tắt thực hành

Mục tiêu **“đọc ghi Extended JSON mà không làm mất thông tin kiểu BSON”** có thể được thực hiện nhất quán theo các nguyên tắc:

1. **Xuất Canonical EJSON v2** khi cần bảo toàn type tags, đặc biệt Int32, Int64, Double, Decimal128, ObjectId, Date và Binary.
2. **Đọc bằng EJSON-aware parser** như EJSON.parse trong mongosh hoặc BsonDocument.parse/Document.parse trong MongoDB Java driver.
3. **Không ép kiểu ngầm** qua JavaScript Number, JSON.stringify, DTO double hoặc chuỗi ngày giờ nếu ứng dụng không chủ ý chuyển đổi.
4. **Dùng mongoexport --jsonFormat=canonical** cho luồng JSON export/import cần giữ BSON type, đồng thời xác nhận mongoimport hỗ trợ EJSON v2.
5. **Kiểm tra giá trị và $type** ở môi trường đích; với dữ liệu quan trọng, kiểm tra cả Decimal128, Int64 lớn, Date và Binary subtype.
6. **Phân biệt dữ liệu document với backup/migration database**: EJSON không bảo toàn toàn bộ schema/index/metadata và không tự tạo snapshot nhất quán.

### Tài liệu tham khảo chính thức

- [MongoDB Extended JSON v2](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — định dạng canonical/relaxed và bảng wrapper của từng BSON type.
- [MongoDB Extended JSON Specification](https://specifications.readthedocs.io/en/latest/extended-json/extended-json/) — hợp đồng chuyển đổi và các giới hạn kỹ thuật.
- [MongoDB Java Sync Driver: Extended JSON](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-extended-json/) — BsonDocument.parse, JsonWriterSettings và JsonMode.
- [mongoexport](https://www.mongodb.com/docs/database-tools/mongoexport/) — tham số --jsonFormat=canonical.
- [mongoimport](https://www.mongodb.com/docs/database-tools/mongoimport/) — nhận dữ liệu EJSON v2 và tùy chọn --legacy.

Khi luồng dữ liệu có nhiều ngôn ngữ lập trình hoặc nhiều công cụ chuyển đổi, hãy xác định từ đầu **kiểu BSON nguồn**, **định dạng EJSON được ghi**, **parser ở đích** và **kiểu dữ liệu ứng dụng sau parse**. Chỉ một bước trung gian thiếu hiểu biết về BSON cũng có thể làm mất thông tin dù file JSON cuối vẫn hoàn toàn hợp lệ.
