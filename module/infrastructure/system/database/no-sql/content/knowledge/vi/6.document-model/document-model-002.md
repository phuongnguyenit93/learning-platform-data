# JSON, BSON hoặc định dạng khác và khác biệt về kiểu dữ liệu

## 1. Tại sao định dạng dữ liệu quan trọng trong mô hình tài liệu?

Trong **document database**, dữ liệu thường được tổ chức thành những **tài liệu (document)** chứa các cặp trường–giá trị. Một tài liệu có thể mang những thông tin liên quan đến cùng một thực thể, ví dụ đơn hàng, sản phẩm hoặc hồ sơ người dùng. Các trường có thể chứa đối tượng lồng nhau và mảng, nhờ đó ứng dụng dễ đọc một nhóm dữ liệu trong cùng một lần truy vấn.

Xét một đơn hàng:

```json
{
  "orderId": "ORD-1001",
  "customerId": "U42",
  "total": 259.90,
  "currency": "USD",
  "createdAt": "2026-11-14T08:30:00Z",
  "paid": true,
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2,
      "unitPrice": 129.95
    }
  ]
}
```

Đây là một **văn bản JSON hợp lệ**. Tuy nhiên, chỉ nhìn JSON chưa thể biết:

- `total` có được lưu bằng số thực nhị phân hay số thập phân chính xác?
- `createdAt` là kiểu thời gian được database nhận biết hay chỉ là chuỗi ký tự?
- `orderId` có được dùng làm khóa chính hay vẫn có trường định danh nội bộ?
- Nếu ID lớn hơn giới hạn số nguyên an toàn của JavaScript, có bị đổi giá trị khi đi qua API không?
- Khi gửi tài liệu từ Java sang cơ sở dữ liệu, driver có giữ được ý nghĩa của từng kiểu hay không?

Các câu hỏi trên cho thấy cần phân biệt **mô hình dữ liệu**, **định dạng biểu diễn dữ liệu** và **kiểu dữ liệu thực tế mà database lưu/truy vấn**.

Một document database có thể tiếp nhận dữ liệu giống JSON ở giao diện lập trình nhưng lưu dưới dạng nhị phân có thêm kiểu, ví dụ BSON. Ngược lại, một sản phẩm dùng JSON làm định dạng chính vẫn có thể có cách biểu diễn, lập chỉ mục và lưu trữ nội bộ riêng. Không thể suy luận kiểu dữ liệu thực tế chỉ từ hình dạng mà API trả về.

## 2. Ba lớp cần phân biệt

```text
       Lớp nghiệp vụ
  Order, Product, User, Event
               |
               v
       Mô hình tài liệu
  document, field, array, subdocument
               |
               v
      Biểu diễn / truyền tải
  JSON, Extended JSON, BSON,
  CBOR, MessagePack, ... (tùy hệ)
               |
               v
    Kiểu dữ liệu và lưu trữ DB
  string, int, long, decimal, date,
  binary, index, codec, storage engine
```

- **Mô hình tài liệu** mô tả cách nhóm thông tin thành một đối tượng có trường, giá trị, mảng và cấu trúc lồng nhau.
- **Định dạng biểu diễn** quy định tài liệu được mã hóa thành chuỗi byte nào khi lưu, truyền qua mạng, xuất/nhập dữ liệu hoặc ghi log.
- **Hệ kiểu dữ liệu** quyết định database có phân biệt chuỗi với thời gian, số nguyên với số thập phân, định danh nhị phân với chuỗi ký tự hay không; các phân biệt này có thể ảnh hưởng so sánh, chỉ mục, sắp xếp và chuyển đổi.

Không phải database nào cũng dùng cả ba lớp theo đúng một cách. Ví dụ MongoDB có cấu trúc tài liệu BSON; API REST thường trao đổi JSON; ứng dụng Java làm việc với đối tượng, `Document`, POJO hoặc các lớp BSON chuyên dụng qua driver.

## 3. JSON: định dạng văn bản phổ biến và tập kiểu cơ bản

**JSON (JavaScript Object Notation)** là định dạng trao đổi dữ liệu dạng văn bản, độc lập với ngôn ngữ lập trình ở mức cú pháp. JSON rất phổ biến trong API HTTP, file cấu hình, message và dịch vụ xử lý dữ liệu.

JSON chuẩn có các loại giá trị sau:

| Kiểu JSON | Ví dụ | Ý nghĩa |
|---|---|---|
| Object | `{"name":"An"}` | Tập cặp tên trường và giá trị |
| Array | `["java","nosql"]` | Danh sách giá trị có thứ tự |
| String | `"ORD-1001"` | Chuỗi Unicode |
| Number | `42`, `19.95`, `-3.5e2` | Giá trị số theo cú pháp JSON |
| Boolean | `true`, `false` | Giá trị logic |
| Null | `null` | Giá trị null tường minh |

Một tài liệu JSON có thể lồng object/array tùy theo cấu trúc dữ liệu. Ví dụ:

```json
{
  "userId": "U42",
  "profile": {
    "displayName": "An",
    "preferences": {
      "language": "vi",
      "notifications": true
    }
  },
  "roles": ["reader", "member"],
  "lastLogin": null
}
```

### 3.1. Những điều JSON không thể hiện trực tiếp

JSON **không có loại giá trị chuẩn riêng** cho:

- Ngày và giờ (Date, Timestamp);
- Số nguyên 32 bit, số nguyên 64 bit hoặc số nguyên độ dài tùy ý;
- Số thập phân chính xác kiểu Decimal128;
- Dữ liệu nhị phân thô, UUID có kiểu hoặc ObjectId;
- Biểu thức chính quy như một kiểu dữ liệu;
- Giá trị phân biệt `NaN`, `Infinity` hay `-Infinity` theo chuẩn JSON.

Chẳng hạn:

```json
{
  "createdAt": "2026-11-14T08:30:00Z",
  "receipt": "AAECAw==",
  "externalId": "9007199254740993"
}
```

Cả ba trường trên **đều là string trong JSON**. Ứng dụng có thể diễn giải chúng lần lượt là thời gian ISO 8601, dữ liệu Base64 và định danh số lớn, nhưng JSON tự nó không gắn các kiểu đó vào giá trị.

Điều này tạo ra sự khác biệt giữa:

1. **Giá trị trong tài liệu JSON**: được parser nhận dưới dạng số, chuỗi, null, object...;
2. **Ý nghĩa nghiệp vụ**: một trường mô tả ngày thanh toán, giá, mã sản phẩm hay nội dung file;
3. **Kiểu thực tế trong database**: có thể là kiểu riêng như BSON Date, Decimal128 hoặc Binary.

### 3.2. Cú pháp JSON và một vài lưu ý

- Tên trường của object phải là chuỗi đặt trong dấu ngoặc kép.
- JSON không hỗ trợ comment và dấu phẩy cuối danh sách theo cú pháp chuẩn.
- Tên trường trùng lặp nên tránh; các parser/hệ thống có thể xử lý không thống nhất.
- Thứ tự phần tử trong array có ý nghĩa; thứ tự các trường object thường không nên dùng làm quy tắc nghiệp vụ.
- JSON number có cú pháp chung, nhưng **độ chính xác và kiểu số khi parse** phụ thuộc ngôn ngữ và thư viện.

Ví dụ, chuỗi dưới đây không phải JSON hợp lệ vì có comment và dấu phẩy cuối:

```javascript
{
  "name": "Product A", // JSON chuẩn không cho phép comment
  "price": 100,
}
```

Một parser chấp nhận đoạn trên đang dùng phần mở rộng hoặc chế độ cú pháp khác. Đừng giả định API và database khác cũng chấp nhận.

## 4. BSON: tài liệu nhị phân có thông tin kiểu

**BSON (Binary JSON)** là định dạng mã hóa tài liệu nhị phân, được sử dụng chủ đạo trong MongoDB để biểu diễn các document. BSON giữ ý tưởng đối tượng gồm trường và giá trị, đồng thời cung cấp **nhiều kiểu dữ liệu hơn JSON chuẩn**.

Điểm cần nhớ: BSON không đơn thuần là “chuỗi JSON được nén”. Nó có cấu trúc nhị phân, thẻ kiểu cho từng phần tử và cách mã hóa riêng cho các kiểu như số nguyên, ngày giờ và ObjectId. Kích thước BSON **không đảm bảo nhỏ hơn JSON**; BSON có thể lớn hơn vì metadata, tên trường và cách mã hóa. Nén ở tầng lưu trữ hoặc mạng là cơ chế khác.

### 4.1. Các kiểu dữ liệu BSON quan trọng

| Kiểu BSON | Ví dụ theo mã ứng dụng/MongoDB | Công dụng |
|---|---|---|
| String | `"Laptop"` | Chuỗi văn bản |
| Boolean | `true` | Cờ trạng thái |
| Null | `null` | Null tường minh |
| Embedded document | `{"cpu":"8-core"}` | Đối tượng lồng nhau |
| Array | `["blue","black"]` | Danh sách có thứ tự |
| Int32 | `NumberInt("42")` | Số nguyên có dấu 32 bit |
| Int64 / Long | `NumberLong("9007199254740993")` | Số nguyên có dấu 64 bit |
| Double | `12.75` | Số thực nhị phân IEEE 754 double |
| Decimal128 | `NumberDecimal("19.99")` | Số thập phân 128 bit, phù hợp phép tính thập phân chính xác trong giới hạn kiểu |
| ObjectId | `ObjectId("507f1f77bcf86cd799439011")` | Định danh BSON 12 byte, thường làm `_id` |
| Date | `ISODate("2026-11-14T08:30:00Z")` | Thời điểm UTC lưu bằng số mili giây |
| Binary | `BinData(...)` | Dãy byte, có subtype |
| Timestamp | `Timestamp(...)` | Kiểu timestamp BSON riêng, có thành phần thời gian và bộ đếm |
| Regular Expression | `/java/i` | Biểu thức chính quy kiểu BSON |
| MinKey / MaxKey | `MinKey()`, `MaxKey()` | Giá trị đặc biệt dùng trong thứ tự so sánh/giới hạn |

Các biểu thức như `ObjectId(...)`, `NumberDecimal(...)` và `ISODate(...)` là **helper/biểu diễn của công cụ MongoDB hoặc mã driver**, không phải cú pháp JSON chuẩn.

BSON còn có một số kiểu lịch sử như Undefined, Symbol, DBPointer hoặc Code; nhiều kiểu mang tính legacy hoặc không nên dùng cho thiết kế mới. Khi trao đổi dữ liệu giữa công nghệ khác nhau, cần xác minh những kiểu được driver đích hỗ trợ.

### 4.2. BSON mở rộng kiểu nhưng vẫn giữ cấu trúc document

Một bản ghi MongoDB có thể mang những kiểu mà JSON không phân biệt:

```javascript
// Ví dụ chạy trong mongosh
db.orders.insertOne({
  _id: new ObjectId(),
  customerId: "U42",
  itemCount: NumberInt(2),
  total: NumberDecimal("259.90"),
  createdAt: ISODate("2026-11-14T08:30:00Z"),
  paid: true,
  tags: ["new", "priority"],
  metadata: {
    source: "mobile"
  }
});
```

Ở đây:

- `_id` là BSON ObjectId thay vì string.
- `itemCount` được chọn là Int32.
- `total` là Decimal128, khác với Double.
- `createdAt` là BSON Date, khác với một chuỗi ISO 8601 thông thường.
- `tags` và `metadata` vẫn là array và embedded document.

Cần nhớ rằng nhiều trình xem dữ liệu **hiển thị** những kiểu BSON bằng văn bản tiện đọc; phần hiển thị không đồng nghĩa với kiểu lưu là string.

### 4.3. Kích thước và giới hạn sản phẩm

BSON là định dạng, còn MongoDB là hệ quản trị có quy tắc riêng. Ví dụ, MongoDB giới hạn kích thước một tài liệu BSON thông thường ở **16 MiB**. Đây là **giới hạn của MongoDB cho một tài liệu**, không phải quy tắc “mọi document database chỉ chứa tối đa 16 MiB”.

Nếu dữ liệu lớn như ảnh, video hoặc file đính kèm, cân nhắc dùng object storage, GridFS hoặc giải pháp lưu file phù hợp, rồi giữ metadata và khóa tham chiếu trong document.

## 5. JSON và BSON khác nhau như thế nào?

| Tiêu chí | JSON | BSON |
|---|---|---|
| Dạng mã hóa | Văn bản Unicode, thường truyền bằng UTF-8 | Nhị phân theo đặc tả BSON |
| Khả năng đọc trực tiếp | Con người thường đọc được bằng trình soạn thảo | Cần bộ giải mã hoặc công cụ hiển thị |
| Kiểu số | Một cú pháp `number`, kiểu cụ thể do parser quyết định | Phân biệt Int32, Int64, Double, Decimal128 |
| Kiểu thời gian | Không có kiểu riêng; thường dùng string | Có Date, Timestamp riêng |
| Định danh | Thường là string hoặc number | Có ObjectId và Binary |
| Dữ liệu nhị phân | Thường mã hóa thành chuỗi Base64 | Có Binary trực tiếp |
| Tính tương tác hệ thống | Rộng rãi trên hầu hết API/ngôn ngữ | Cần thư viện BSON/driver tương thích |
| Kích thước | Tùy dữ liệu và kiểu số/chuỗi | Không mặc định nhỏ hơn; tùy trường và kiểu |
| Thông tin kiểu khi chuyển đổi | Có thể mất kiểu đặc thù | Giữ được kiểu BSON nếu đi qua codec phù hợp |

Ví dụ hai giá trị JSON:

```json
{
  "count": 42,
  "amount": 19.99
}
```

Một parser JavaScript thường tạo hai giá trị kiểu `Number`. BSON có thể lưu `count` là Int32 và `amount` là Decimal128 nếu ứng dụng khai báo rõ. Sự lựa chọn này ảnh hưởng phép toán, chính xác số và cách chuyển đổi qua driver.

## 6. Extended JSON (EJSON): biểu diễn kiểu BSON bằng JSON

Khi cần xuất/nhập BSON dưới dạng văn bản, MongoDB sử dụng **Extended JSON**. Ý tưởng là thêm những object wrapper có khóa đặc biệt để bảo toàn kiểu BSON.

### 6.1. JSON thông thường có thể mất kiểu

Giả sử tài liệu trong MongoDB chứa:

- `_id` kiểu ObjectId;
- `amount` kiểu Decimal128;
- `createdAt` kiểu BSON Date;
- `externalId` kiểu Int64 rất lớn.

Nếu xuất đơn giản ra:

```json
{
  "_id": "507f1f77bcf86cd799439011",
  "amount": 19.99,
  "createdAt": "2026-11-14T08:30:00Z",
  "externalId": 9007199254740993
}
```

Một hệ thống nhận dữ liệu có thể hiểu ID và ngày là chuỗi, số tiền là double, còn externalId có thể bị làm tròn trong JavaScript. Khi ghi ngược vào MongoDB, những kiểu ban đầu chưa chắc được khôi phục.

### 6.2. Extended JSON dạng Canonical

Ví dụ minh họa:

```json
{
  "_id": {
    "$oid": "507f1f77bcf86cd799439011"
  },
  "amount": {
    "$numberDecimal": "19.99"
  },
  "itemCount": {
    "$numberInt": "2"
  },
  "externalId": {
    "$numberLong": "9007199254740993"
  },
  "createdAt": {
    "$date": {
      "$numberLong": "0"
    }
  }
}
```

Trong đoạn trên, `createdAt` được cố ý dùng mốc **Unix epoch 1970-01-01T00:00:00Z** để minh họa số mili giây `0`; giá trị này không phải ngày tạo đơn ở ví dụ trước.

Các wrapper như `$oid`, `$numberDecimal`, `$numberInt`, `$numberLong` và `$date` cho phép **bộ giải mã EJSON hiểu và khôi phục kiểu BSON**. Nếu chỉ gọi `JSON.parse(...)` thông thường, kết quả vẫn là các object JSON có trường mang tên `$oid`, `$date`...; nó chưa tự tạo ObjectId hay Decimal128.

### 6.3. Extended JSON dạng Relaxed

Dạng Relaxed ưu tiên dễ đọc; một số giá trị có thể biểu diễn trực tiếp bằng số JSON, và ngày có thể hiển thị bằng chuỗi ISO trong wrapper.

```json
{
  "_id": { "$oid": "507f1f77bcf86cd799439011" },
  "itemCount": 2,
  "amount": { "$numberDecimal": "19.99" },
  "createdAt": { "$date": "2026-11-14T08:30:00Z" }
}
```

Dạng Canonical thường hữu ích khi **cần giữ phân biệt kiểu khi xuất/nhập**, còn Relaxed thuận tiện cho con người đọc và trao đổi. Cần kiểm tra liệu quy trình xuất/nhập có thực sự yêu cầu bảo toàn Int32/Int64/Double khác nhau hay không; không nên chỉ dựa vào hình dạng dễ nhìn để kết luận kiểu được giữ nguyên.

| Giá trị BSON | Biểu diễn EJSON Canonical minh họa | Ghi chú |
|---|---|---|
| ObjectId | `{"$oid":"507f1f77bcf86cd799439011"}` | Không tương đương string thường |
| Int32 | `{"$numberInt":"42"}` | Phân biệt 32 bit |
| Int64 | `{"$numberLong":"9007199254740993"}` | Tránh làm tròn qua number của JS |
| Decimal128 | `{"$numberDecimal":"19.99"}` | Giữ ý nghĩa thập phân |
| Date | `{"$date":{"$numberLong":"0"}}` | Mili giây UTC từ Unix epoch |
| Binary | `{"$binary":{"base64":"AAECAw==","subType":"00"}}` | Dữ liệu byte và subtype |

EJSON không thay thế định nghĩa schema nghiệp vụ. Một key đặc biệt trông giống wrapper có thể có ý nghĩa khác trong hệ thống JSON thường; cần dùng **đúng parser, đúng phiên bản chuẩn EJSON và đúng mục đích xuất/nhập**.

## 7. Khác biệt về kiểu số: vấn đề dễ gây lỗi nhất

### 7.1. JSON number khác số kiểu cụ thể

JSON quy định cách viết giá trị số, chẳng hạn `1`, `1.25` hay `1e6`, nhưng không buộc mọi ngôn ngữ đọc thành cùng một kiểu máy.

Trong Java:

- `int` chứa số nguyên 32 bit.
- `long` chứa số nguyên 64 bit.
- `double` là số thực nhị phân, có giới hạn độ chính xác.
- `BigInteger` hỗ trợ số nguyên rất lớn.
- `BigDecimal` hỗ trợ số thập phân với độ chính xác thập phân được kiểm soát.

Trong JavaScript, `Number` thường là số thực IEEE 754 double. Những số nguyên lớn hơn **2^53 - 1 = 9.007.199.254.740.991** không còn được biểu diễn chính xác cho mọi giá trị nguyên.

Ví dụ:

```javascript
const payload = JSON.parse('{"externalId":9007199254740993}');
console.log(payload.externalId);
// Thường in ra 9007199254740992 vì Number không giữ nguyên số này.

console.log(Number.isSafeInteger(payload.externalId));
// false
```

Nếu số đó là ID, sai khác chỉ 1 đơn vị cũng là lỗi nghiêm trọng. Đối với API JSON đi qua JavaScript hoặc các hệ thống không thống nhất kiểu số, định danh lớn nên được **truyền dưới dạng string có quy ước** hoặc bằng định dạng có kiểu/codec phù hợp.

### 7.2. Int32, Int64 và Double trong BSON

Trong BSON:

- **Int32** là số nguyên có dấu 32 bit.
- **Int64** là số nguyên có dấu 64 bit.
- **Double** là số thực nhị phân 64 bit.
- **Decimal128** là số thập phân theo dạng decimal floating-point, có độ chính xác hữu hạn.

Không nên tự động xem:

```text
Int32(42)
Int64(42)
Double(42.0)
Decimal128("42")
String("42")
```

là cùng một kiểu lưu trữ. Một số database, trong đó có MongoDB, có thể so sánh các kiểu số dựa trên giá trị trong nhiều truy vấn; tuy nhiên, **string vẫn không phải kiểu số**, và quá trình chuyển đổi/tuần tự hóa, công cụ truy cập cũng như thao tác số học còn chịu quy tắc riêng.

Ví dụ, tài liệu lưu `quantity` dưới dạng string:

```json
{
  "quantity": "10"
}
```

không tương đương với:

```json
{
  "quantity": 10
}
```

Khi so sánh chuỗi, thứ tự từ điển có thể khiến `"10"` đứng trước `"2"`; còn khi so sánh số thì 10 lớn hơn 2. Do vậy không nên dùng string để thay kiểu số chỉ vì chúng trông giống nhau.

### 7.3. Double và số tiền

Số thực nhị phân không biểu diễn chính xác mọi phân số thập phân, trong đó có `0.1` và `0.2`.

```javascript
console.log(0.1 + 0.2 === 0.3);
// false
```

Với số tiền, có hai cách phổ biến:

1. **Decimal128 / BigDecimal** cho những phép tính thập phân trong giới hạn độ chính xác của kiểu và quy tắc làm tròn được quy định.
2. **Số nguyên đơn vị nhỏ nhất** (ví dụ cents) để biểu diễn số tiền có độ chia cố định; phải quy định rõ tiền tệ và tỷ lệ quy đổi.

Ví dụ tài liệu với Decimal128 trong mongosh:

```javascript
db.payments.insertOne({
  _id: "pay-1001",
  currency: "USD",
  amount: NumberDecimal("19.99")
});
```

Tương đương trong Java bằng `BigDecimal` và kiểu BSON `Decimal128`:

```java
import java.math.BigDecimal;
import org.bson.types.Decimal128;

BigDecimal amount = new BigDecimal("19.99");
Decimal128 bsonAmount = new Decimal128(amount);
```

Đối với `BigDecimal` trong Java, dùng chuỗi `"19.99"` giúp tránh đưa sai số double có sẵn vào dữ liệu:

```java
BigDecimal good = new BigDecimal("0.1");
BigDecimal risky = new BigDecimal(0.1);
// risky nhận đúng giá trị double được truyền vào,
// vốn không biểu diễn thập phân 0.1 một cách chính xác.
```

Cần xác định quy tắc làm tròn, phạm vi giá trị và độ chính xác nghiệp vụ từ trước. Decimal128 có độ chính xác khoảng **34 chữ số thập phân có nghĩa**, không phải số thập phân vô hạn.

### 7.4. Lưu kiểu số nhất quán

Nếu collection có tài liệu lưu `price` là Double, tài liệu khác là Decimal128, một nhóm khác là string, hệ thống có thể gặp khó khăn khi truy vấn, tính tổng, chuyển đổi driver và so sánh.

Một thiết kế tốt nên quy định:

- `price` lưu kiểu nào?
- `quantity` là Int32 hay Int64?
- `externalId` là string hay số nguyên lớn?
- Có chấp nhận giá trị âm và bằng 0 không?
- Dữ liệu cũ có kiểu khác thì xử lý/migrate ra sao?
- API JSON có đi qua JavaScript hoặc hệ không giữ chính xác Int64 không?

## 8. Ngày giờ: chuỗi ISO 8601 khác BSON Date

### 8.1. String trông giống ngày vẫn chỉ là string

Hai tài liệu sau không tương đương:

```javascript
// Dùng chuỗi
{ createdAt: "2026-11-14T08:30:00Z" }

// Dùng BSON Date trong mongosh
{ createdAt: ISODate("2026-11-14T08:30:00Z") }
```

Với trường kiểu Date, database có thể hỗ trợ phép so sánh và chỉ mục theo thời điểm. Với string, hệ thống so sánh văn bản theo quy tắc của string. Nếu mọi giá trị string được chuẩn hóa cùng định dạng UTC có độ rộng cố định, thứ tự từ điển đôi khi tương ứng thứ tự thời gian; nhưng khi có múi giờ, độ chính xác, định dạng hoặc cách ghi khác nhau, giả định này dễ vỡ.

Ví dụ hai cách viết cùng một thời điểm:

```text
2026-11-14T08:30:00Z
2026-11-14T15:30:00+07:00
```

Chúng biểu thị cùng một thời điểm nhưng không có chuỗi ký tự giống nhau. Vì vậy, lưu ngày như string rồi sắp xếp từ điển dễ gây lỗi nếu không có quy ước chuẩn hóa cực kỳ chặt.

### 8.2. BSON Date thực chất lưu gì?

BSON Date biểu diễn một thời điểm bằng **số nguyên có dấu 64 bit đếm mili giây từ Unix epoch UTC**. Nó không lưu kèm tên múi giờ như `Asia/Ho_Chi_Minh`. Khi hiển thị, ứng dụng có thể chuyển thời điểm đó sang múi giờ của người dùng.

Trong Java, `Instant` mô tả một thời điểm trên trục UTC; MongoDB Java driver có thể làm việc với `java.util.Date` hoặc codec/kiểu Java time được cấu hình thích hợp.

```java
import java.time.Instant;
import java.util.Date;

Instant createdAt = Instant.parse("2026-11-14T08:30:00Z");
Date bsonCompatibleDate = Date.from(createdAt);
```

Việc chuyển `Instant` sang BSON Date có **độ phân giải mili giây**. Nếu dữ liệu nguồn có nanosecond, phần độ chính xác vượt mili giây không được bảo toàn trong kiểu BSON Date thông thường.

### 8.3. BSON Timestamp không phải Date

BSON có kiểu riêng mang tên **Timestamp**, thường dùng cho mục đích nội bộ hoặc cơ chế thứ tự sự kiện/changelog trong MongoDB. Nó có thành phần thời gian và bộ đếm. Đừng chọn BSON Timestamp chỉ vì một trường mang tên `createdAt` hoặc `updatedAt`.

Đối với thời điểm nghiệp vụ như ngày tạo đơn hoặc thời gian đăng nhập, thông thường nên dùng **BSON Date** hoặc một quy ước thời gian có giải thích rõ.

### 8.4. Cẩn thận khi so sánh giá trị

Giả sử trường `createdAt` trong database là BSON Date, dùng truy vấn MongoDB:

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-14T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
});
```

Truyền trực tiếp hai chuỗi ISO thay cho giá trị BSON Date có thể không cho kết quả như mong đợi do hệ kiểu dữ liệu. Ứng dụng nên chuyển thời điểm đầu vào thành **kiểu Date của driver** trước khi xây truy vấn.

## 9. Định danh: String, ObjectId, UUID và số nguyên lớn

### 9.1. String và ObjectId khác kiểu

MongoDB thường sinh `_id` kiểu **ObjectId** nếu ứng dụng không cung cấp `_id`. ObjectId là định danh nhị phân 12 byte, thường hiển thị bằng 24 ký tự hex.

Ví dụ cùng chuỗi ký tự hex:

```javascript
const textId = "507f1f77bcf86cd799439011";
const typedId = ObjectId(textId);

// Không nên cho rằng đây là cùng một kiểu điều kiện lọc.
db.products.findOne({ _id: textId });
db.products.findOne({ _id: typedId });
```

Nếu `_id` được lưu dưới dạng ObjectId, điều kiện dùng string thường **không khớp cùng ID**. Cần parse, kiểm tra hợp lệ và dùng đúng kiểu driver.

### 9.2. ObjectId không phải timestamp nghiệp vụ

ObjectId thường chứa một phần gắn với thời điểm tạo ở độ phân giải giây, nhưng điều đó không khiến nó trở thành ngày tạo đáng tin cậy tuyệt đối:

- ID có thể được tạo ở phía client trước khi tài liệu được lưu;
- Đồng hồ các client có thể khác nhau;
- Phần timestamp không đủ độ phân giải cho nhiều sự kiện trong một giây;
- Thứ tự toàn cục giữa nhiều máy không phải luôn được bảo đảm.

Vì vậy, nếu nghiệp vụ cần truy vấn, hiển thị hoặc kiểm tra thời gian tạo, nên lưu trường `createdAt` kiểu Date riêng.

### 9.3. UUID và Binary

UUID thường biểu diễn 128 bit. Trong BSON, ứng dụng có thể lưu dưới dạng **Binary** với subtype phù hợp. Với MongoDB, UUID chuẩn thường sử dụng **binary subtype 4**; một số hệ thống/driver cũ đã dùng cách biểu diễn legacy khác.

Nếu hai dịch vụ dùng UUID nhưng khác cách ánh xạ byte hoặc subtype, cùng UUID ở dạng văn bản có thể không được lưu thành cùng dãy byte. Khi tích hợp, cần thống nhất:

- Dùng string UUID hay Binary UUID?
- Nếu Binary, dùng subtype nào?
- Driver và cấu hình `UuidRepresentation` như thế nào?
- Khi chuyển giữa Java và một ngôn ngữ khác, có kiểm tra khả năng đọc chéo không?

Một chuỗi UUID dễ trao đổi qua JSON nhưng chiếm nhiều ký tự hơn; Binary có thể tiết kiệm dạng biểu diễn và cung cấp kiểu rõ hơn khi hệ thống hỗ trợ.

### 9.4. Định danh không nhất thiết là số

Nhiều hệ tạo ID bằng chuỗi như `"ORD-2026-000001"`, ULID hoặc UUID. Việc chọn kiểu phụ thuộc yêu cầu tạo ID, phân vùng, tính duy nhất, khả năng nhập/xuất và quy tắc nghiệp vụ. Không cần chuyển một ID sang number chỉ vì nó chứa toàn chữ số.

## 10. Dữ liệu nhị phân, văn bản và mã hóa Base64

JSON không có kiểu byte array độc lập nên API thường biểu diễn dữ liệu nhị phân bằng **chuỗi Base64**:

```json
{
  "mimeType": "image/png",
  "contentBase64": "AAECAw=="
}
```

Base64 làm dữ liệu lớn hơn so với byte thô vì mỗi 3 byte thường được biểu diễn bởi khoảng 4 ký tự (chưa tính phần khác). BSON có kiểu **Binary** để lưu trực tiếp byte và subtype.

Biểu diễn Extended JSON của Binary:

```json
{
  "content": {
    "$binary": {
      "base64": "AAECAw==",
      "subType": "00"
    }
  }
}
```

Nếu lưu một ảnh lớn trong document:

- Mỗi lần đọc toàn bộ document có thể kéo theo lượng byte lớn;
- Tài liệu có thể chạm giới hạn kích thước của sản phẩm;
- Cập nhật metadata nhỏ có thể khó vận hành hơn nếu dữ liệu nhị phân gắn cùng document lớn;
- Truyền hình ảnh qua API có thể phù hợp hơn với file/object storage và URL có kiểm soát truy cập.

Vì thế, thường nên lưu trong document các trường `fileId`, `contentType`, `size`, `checksum` và thông tin quyền truy cập; nội dung file được lưu ở kho phù hợp. Lựa chọn cuối cùng phụ thuộc kích thước, tải và yêu cầu giao dịch.

## 11. Null, trường không tồn tại và giá trị mặc định

Đây là khác biệt quan trọng giữa **kiểu dữ liệu** và **sự hiện diện của trường**.

Xét ba document:

```javascript
{ _id: 1, phone: null }
{ _id: 2 }
{ _id: 3, phone: "" }
```

Ý nghĩa có thể là:

- Document 1: trường `phone` tồn tại và chứa `null`.
- Document 2: **không có trường `phone`**.
- Document 3: trường tồn tại nhưng chứa chuỗi rỗng.

Trong MongoDB, điều kiện:

```javascript
db.users.find({ phone: null });
```

có thể khớp cả document có `phone: null` **và** document thiếu trường `phone`. Nếu nghiệp vụ cần phân biệt, dùng các điều kiện thích hợp:

```javascript
// Trường không tồn tại
db.users.find({ phone: { $exists: false } });

// Trường tồn tại, có giá trị null
db.users.find({ phone: { $exists: true, $eq: null } });

// Trường tồn tại với kiểu string (bao gồm string rỗng)
db.users.find({ phone: { $type: "string" } });
```

Quy tắc khớp null/missing có thể khác giữa những database hoặc ngôn ngữ truy vấn. Không nên mặc định mọi hệ document xử lý giống MongoDB.

### 11.1. API và ứng dụng cần quy ước null rõ ràng

Trong một request cập nhật một phần:

```json
{
  "displayName": "An"
}
```

có thể có nghĩa là “chỉ sửa displayName, giữ nguyên các trường khác”. Trong khi:

```json
{
  "displayName": "An",
  "phone": null
}
```

có thể mang nghĩa “xóa/đặt trống phone”, tùy định nghĩa API. Nếu code Java tự thêm tất cả trường thiếu vào document với giá trị null, ứng dụng có thể vô tình xóa dữ liệu.

Hãy phân biệt **không gửi**, **gửi null**, **gửi chuỗi rỗng** và **gửi giá trị hợp lệ** ở lớp request, validation và cập nhật database.

## 12. Mảng, document lồng nhau và ngữ nghĩa truy vấn

Document database thường cho phép trường có kiểu array và embedded document:

```json
{
  "orderId": "ORD-1001",
  "items": [
    { "sku": "A", "qty": 1 },
    { "sku": "B", "qty": 5 }
  ],
  "shipping": {
    "city": "Ho Chi Minh City",
    "country": "VN"
  }
}
```

Một điểm dễ nhầm là điều kiện áp lên các trường bên trong array.

Giả sử MongoDB có document:

```javascript
{
  orderId: "ORD-1001",
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 5 }
  ]
}
```

Điều kiện:

```javascript
db.orders.find({
  "items.sku": "A",
  "items.qty": { $gte: 5 }
});
```

có thể khớp vì **một phần tử** có `sku = "A"` và **phần tử khác** có `qty >= 5`.

Nếu muốn cùng một phần tử đáp ứng cả hai:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "A",
      qty: { $gte: 5 }
    }
  }
});
```

Đây là sự khác biệt về **ngữ nghĩa truy vấn trên cấu trúc mảng**, không chỉ cách viết JSON.

### 12.1. Lựa chọn nhúng hay tham chiếu

Nhúng phù hợp khi dữ liệu phụ nhỏ, có số lượng giới hạn và thường được đọc cùng nhau. Khi mảng có thể tăng đến hàng triệu phần tử, việc nhúng có thể tạo tài liệu rất lớn, gây chi phí cập nhật và đọc.

Ví dụ, `order.items` của một đơn hàng thông thường có kích thước hữu hạn; còn `product.pageViews` ghi một phần tử mỗi lần xem có thể tăng không giới hạn. Với page views, nên cân nhắc một collection sự kiện, time-series hoặc mô hình phù hợp.

### 12.2. Chỉ mục trên mảng

Một số hệ document, ví dụ MongoDB, có **multikey index** để lập chỉ mục các phần tử array. Tuy nhiên, việc kết hợp nhiều trường array trong chỉ mục hoặc tìm các phần tử thỏa điều kiện cần tuân thủ những quy tắc của engine. Không nên giả định mọi truy vấn array lồng nhau đều dùng cùng một chỉ mục hiệu quả.

## 13. Kiểu trong Java và ánh xạ qua MongoDB Java Driver

Trong dự án Java, dữ liệu đi qua nhiều lớp:

```text
JSON từ HTTP
     |
     v
Jackson / JSON parser
     |
     v
DTO / Java class
     |
     v
MongoDB Java Driver + codecs
     |
     v
BSON document trong MongoDB
```

Ở mỗi lớp, cần kiểm soát cách ánh xạ kiểu. Một JSON parser có thể tạo `Integer`, `Long`, `Double`, `BigDecimal` hoặc `BigInteger` tùy cấu hình và cách ứng dụng dùng; driver sau đó mã hóa thành kiểu BSON tương ứng nếu được hỗ trợ.

### 13.1. Tạo document có kiểu rõ ràng trong Java

Ví dụ sau sử dụng các kiểu của MongoDB Java Driver (cần khai báo dependency driver phù hợp trong dự án):

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;
import java.util.List;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;

public class OrderDocumentExample {
    public static Document createOrder() {
        return new Document("_id", new ObjectId())
                .append("orderId", "ORD-1001")
                .append("itemCount", Integer.valueOf(2))
                .append("externalId", Long.valueOf(9_007_199_254_740_993L))
                .append("total", new Decimal128(new BigDecimal("259.90")))
                .append("createdAt", Date.from(
                        Instant.parse("2026-11-14T08:30:00Z")))
                .append("paid", Boolean.TRUE)
                .append("tags", List.of("new", "priority"));
    }
}
```

Ý nghĩa của các giá trị:

| Java | BSON dự kiến khi dùng codec tương ứng | Lưu ý |
|---|---|---|
| `String` | String | Không được tự động nhận là ObjectId/Date |
| `Integer` | Int32 | Kiểm tra phạm vi nếu nguồn lớn |
| `Long` | Int64 | Không ép về JavaScript Number khi truyền JSON |
| `Double` | Double | Không phù hợp cho tính toán tiền cần thập phân chính xác |
| `Decimal128` | Decimal128 | Có giới hạn độ chính xác của Decimal128 |
| `Date` | Date | Mili giây UTC |
| `ObjectId` | ObjectId | Khác string 24 ký tự hex |
| `List<?>` | Array | Kiểu phần tử vẫn quan trọng |
| `Document` | Embedded document | Có thể lồng nhau |

Nếu muốn dùng POJO Java thay `Document`, cần cấu hình codec/serialization phù hợp, nhất là cho `Instant`, `BigDecimal`, enum, UUID và các kiểu do ứng dụng tự định nghĩa. Không nên mặc định mọi lớp tự động ánh xạ ra BSON đúng ý định.

### 13.2. Parse JSON không tự tạo kiểu BSON riêng

Giả sử API nhận:

```json
{
  "createdAt": "2026-11-14T08:30:00Z",
  "total": 259.90
}
```

Nếu code chỉ parse thành một map thông thường, `createdAt` có thể là `String` và `total` có thể là `Double`. Để ghi đúng, cần áp dụng mapping ở lớp ứng dụng:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

import org.bson.Document;
import org.bson.types.Decimal128;

// Ví dụ giả định hai biến đầu vào đã được validate.
// createdAtText: "2026-11-14T08:30:00Z"
// totalText:     "259.90"

Document doc = new Document()
        .append("createdAt",
                Date.from(Instant.parse(createdAtText)))
        .append("total",
                new Decimal128(new BigDecimal(totalText)));
```

Đoạn trên là phần ánh xạ minh họa; `createdAtText` và `totalText` phải được lấy từ lớp đầu vào đã kiểm tra. Với tiền, API nên có quy ước giữ chính xác chữ số thập phân (ví dụ chuỗi thập phân hoặc parser tạo `BigDecimal` từ JSON number) thay vì biến thành Double rồi mới chuyển.

### 13.3. Chuyển Java object sang JSON có thể làm mất thông tin

Các phương thức như `toJson()` của thư viện BSON có thể xuất Extended JSON, khác với JSON API thông thường. Còn serializer JSON chung có thể biến kiểu đặc biệt thành string hoặc object khác tùy cấu hình.

Khi đọc/ghi qua nhiều dịch vụ, nên thử một bộ giá trị ranh giới:

- Int64 lớn hơn `2^53 - 1`;
- Decimal128 có nhiều chữ số thập phân;
- Date có timezone và milliseconds;
- ObjectId/UUID ở dạng binary;
- null, trường thiếu và array lồng nhau.

Những trường này rất dễ bộc lộ sai lệch kiểu khi đi qua lớp chuyển đổi.

## 14. Các định dạng khác: CBOR, MessagePack, Avro, Protobuf và JSONB

Ngoài JSON và BSON, dữ liệu tài liệu có thể được mã hóa hay lưu trữ bằng nhiều định dạng khác. Cần phân biệt **định dạng vận chuyển/serialization** với **mô hình dữ liệu mà database hỗ trợ truy vấn**.

| Định dạng/cơ chế | Đặc điểm chính | Tình huống thường gặp |
|---|---|---|
| JSON | Văn bản, dễ đọc, tương tác rộng | REST API, cấu hình, dữ liệu trao đổi |
| BSON | Nhị phân, có thêm kiểu như ObjectId, Decimal128, Date | Tài liệu MongoDB và các công cụ BSON |
| CBOR | Nhị phân, mô hình dữ liệu tương tự JSON nhưng hỗ trợ nhiều giá trị và tag | Giao thức compact, IoT, trao đổi nhị phân |
| MessagePack | Nhị phân gọn, hỗ trợ map/array và các kiểu số, extension | RPC, cache, message truyền tải |
| Apache Avro | Serialization gắn với schema; hỗ trợ schema evolution có quy tắc | Event stream, data pipeline |
| Protocol Buffers | Định nghĩa message bằng schema, dùng tag trường | Service-to-service RPC, event và storage |
| JSONB | Tên kiểu lưu trữ/biểu diễn JSON ở một số RDBMS như PostgreSQL | Truy vấn JSON trong SQL, chỉ mục và cập nhật |

Đánh giá:

- **JSON** đơn giản để tích hợp, nhưng không giữ nhiều loại kiểu chuyên dụng nếu không quy ước thêm.
- **CBOR/MessagePack** có thể gọn hoặc hiệu quả truyền tải hơn với dữ liệu phù hợp; vẫn phải thống nhất cách diễn giải kiểu và phần mở rộng.
- **Avro/Protobuf** hỗ trợ giao tiếp với cấu trúc được định nghĩa rõ, thuận lợi khi cần kiểm soát thay đổi schema qua nhiều dịch vụ. Chúng không tự biến dữ liệu thành document database có khả năng truy vấn theo trường.
- **JSONB** trong PostgreSQL cho phép lưu và truy vấn JSON trong hệ quan hệ. Tên “JSONB” ở một sản phẩm khác có thể mang ý nghĩa nội bộ khác; không nên coi mọi kiểu mang chữ “B” là BSON hoặc tương thích nhị phân với nhau.

Ví dụ một record Protobuf có thể được định nghĩa:

```proto
syntax = "proto3";

message OrderSummary {
  string order_id = 1;
  int64 external_id = 2;
  string amount_decimal = 3;
  int64 created_at_epoch_millis = 4;
}
```

Ở đây, số trường xác định cách mã hóa; `amount_decimal` được chọn làm string theo quy ước của ví dụ, còn thời gian là số mili giây. Protobuf không có sẵn một “Decimal128 MongoDB” chỉ vì ứng dụng cần tiền. Nếu dùng schema và cách mã hóa khác, cần ghi rõ hợp đồng dữ liệu.

### 14.1. Document database không đồng nghĩa với BSON

Một số sản phẩm lưu trữ hoặc biểu diễn tài liệu dưới dạng JSON, một số có các kiểu riêng và một số dùng BSON. Ví dụ:

- MongoDB gắn chặt với BSON và Extended JSON.
- Couchbase sử dụng mô hình tài liệu JSON và có quy tắc kiểu, chỉ mục, truy vấn riêng.
- DynamoDB có cấu trúc thuộc tính với các loại như String, Number, Binary, Map, List và Set; dạng JSON giao tiếp có thể chứa type descriptor, không phải JSON document thuần.
- Firestore có các kiểu giá trị được định nghĩa riêng, bao gồm timestamp, reference, geopoint, array và map.

Vì vậy, cách tốt nhất để thiết kế ứng dụng là xem **tập kiểu chính thức của đúng database** thay vì mặc định tất cả hỗ trợ BSON hoặc JSON như nhau.

## 15. Kiểu dữ liệu ảnh hưởng trực tiếp đến truy vấn và chỉ mục

Những lỗi về kiểu thường chỉ xuất hiện khi dữ liệu thật tăng lên hoặc nhiều dịch vụ cùng ghi vào một collection.

| Tình huống | Lỗi có thể xảy ra | Hướng phòng tránh |
|---|---|---|
| `createdAt` lưu lúc là string, lúc là Date | Lọc khoảng thời gian thiếu kết quả hoặc sắp xếp sai | Chuẩn hóa kiểu Date và migration dữ liệu cũ |
| `_id` lưu ObjectId nhưng API gửi string | Query theo ID không tìm thấy tài liệu | Chuyển string sang ObjectId có validate |
| `amount` lưu Double xen Decimal128 | Kết quả số học/serialization không thống nhất | Chọn một kiểu thập phân và quy tắc làm tròn |
| ID 64 bit đi qua JS Number | Mất độ chính xác ID | Truyền string hoặc typed serialization |
| `phone` null và missing bị gộp | Update/xóa sai hoặc báo cáo thiếu chính xác | Tách rõ null, missing và empty string |
| Array có nhiều phần tử | Điều kiện lọc có thể khớp ở các phần tử khác nhau | Dùng `$elemMatch` hoặc cú pháp tương ứng |
| UUID lưu nhiều subtype/byte order | Đọc chéo giữa driver ra ID khác | Chuẩn hóa subtype và UUID representation |
| Dữ liệu binary gắn trong tài liệu rất lớn | Đọc/ghi tốn kém, đụng giới hạn document | Tách file/object storage, giữ metadata |

### 15.1. Sắp xếp có thể bị ảnh hưởng bởi kiểu

Nếu một trường lưu các giá trị:

```javascript
{ score: 2 }
{ score: "10" }
{ score: 15 }
{ score: null }
```

kết quả sắp xếp không thể hiểu như “sắp xếp toàn bộ theo giá trị số tăng dần”. Hệ có thể quy định thứ tự giữa các loại BSON khác nhau; chuỗi thì được so sánh theo quy tắc văn bản. Vì vậy, cần dùng kiểu nhất quán và chỉ mục thích hợp.

### 15.2. Index không sửa được dữ liệu sai kiểu

Một chỉ mục được xây dựng trên trường `amount` không tự động làm chuỗi `"19.99"` biến thành Decimal128. Nếu dữ liệu đã lẫn kiểu, cần kế hoạch làm sạch và chuyển đổi trước hoặc song song với quá trình cập nhật ứng dụng.

### 15.3. Validation không đồng nghĩa schema cứng như bảng SQL

Document có thể linh hoạt nhưng ứng dụng vẫn nên có **hợp đồng schema**. MongoDB có thể kiểm tra điều kiện bằng validator; ví dụ minh họa:

```javascript
db.createCollection("payments", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderId", "amount", "createdAt"],
      properties: {
        orderId: { bsonType: "string" },
        amount: { bsonType: "decimal" },
        createdAt: { bsonType: "date" }
      }
    }
  }
});
```

Ví dụ trên cho biết:

- `orderId` phải là string;
- `amount` phải là Decimal128;
- `createdAt` phải là BSON Date;
- cả ba trường phải hiện diện.

Validator này sử dụng **cú pháp MongoDB `$jsonSchema` với `bsonType`**; không nên nhầm với JSON Schema chuẩn hoặc giả định mọi document database hỗ trợ cú pháp giống nhau. Quy tắc validation không thay cho kiểm tra nghiệp vụ (giới hạn số tiền, trạng thái đơn, quyền truy cập, tính duy nhất...).

## 16. Thiết kế schema khi dữ liệu thay đổi theo thời gian

Document database cho phép các tài liệu trong cùng một collection có cấu trúc khác nhau. Đó là tính linh hoạt hữu ích, nhưng cũng tạo rủi ro khi phiên bản cũ và mới cùng tồn tại.

Ví dụ:

**Phiên bản 1:**

```json
{
  "schemaVersion": 1,
  "orderId": "ORD-1001",
  "total": "259.90",
  "createdAt": "2026-11-14T08:30:00Z"
}
```

**Phiên bản 2:**

```javascript
{
  schemaVersion: 2,
  orderId: "ORD-1001",
  total: NumberDecimal("259.90"),
  createdAt: ISODate("2026-11-14T08:30:00Z")
}
```

Hai tài liệu biểu diễn cùng ý nghĩa nhưng khác kiểu. Nếu code mới mặc định `total` luôn là Decimal128, nó có thể đọc lỗi hoặc tính sai với tài liệu cũ còn string.

Một quy trình chuyển đổi có thể gồm:

1. **Xác định hợp đồng kiểu mới** và thống nhất giữa API, ứng dụng, driver và database.
2. **Kiểm tra các dạng đang tồn tại**: trường nào thiếu, null, string, number, Date?
3. **Triển khai code đọc tương thích** trong giai đoạn chuyển tiếp nếu cần.
4. **Ghi dữ liệu mới theo chuẩn**; tránh tiếp tục tạo thêm kiểu cũ.
5. **Backfill/migrate dữ liệu cũ** bằng thao tác có kiểm soát, có ghi nhận lỗi.
6. **Bật validation** với chính sách thích hợp sau khi dữ liệu và các producer đã tương thích.
7. **Loại đường đọc kiểu cũ** khi dữ liệu và hệ tích hợp đã chuyển xong.

Tránh xem việc đổi tên hoặc đổi kiểu trường là một sửa đổi nhỏ. Cả bộ lọc, chỉ mục, sort, aggregation, API và message stream có thể bị ảnh hưởng.

### 16.1. Không tự động ép kiểu vô điều kiện

Ví dụ `amount = "N/A"`, `amount = ""` và `amount = "259.90"` đều là string nhưng chỉ một giá trị là tiền hợp lệ. Migration cần có quy tắc xử lý dữ liệu không thể chuyển đổi, thay vì thay tất cả bằng 0 rồi làm sai báo cáo.

Tương tự, một chuỗi thời gian không có múi giờ như `"2026-11-14 08:30:00"` không thể được chuyển chính xác thành thời điểm UTC nếu chưa biết quy ước múi giờ ban đầu.

## 17. Ví dụ xuyên suốt: thiết kế tài liệu đơn hàng an toàn

Một mô hình đơn hàng có thể chọn:

| Trường | Kiểu đề xuất | Lý do |
|---|---|---|
| `_id` | ObjectId hoặc string ID nhất quán | Khóa định danh |
| `orderId` | String | Mã đơn nghiệp vụ có định dạng riêng |
| `customerId` | String hoặc cùng kiểu ID với collection khách hàng | Dễ truy vấn và tham chiếu |
| `total` | Decimal128 | Tiền với phép toán thập phân |
| `currency` | String | Mã tiền tệ có quy tắc kiểm tra |
| `createdAt` | Date | Truy vấn và sắp theo thời điểm |
| `itemCount` | Int32 | Số lượng trong phạm vi cho phép |
| `items` | Array các embedded document có giới hạn | Chi tiết được đọc cùng đơn hàng |
| `schemaVersion` | Int32 | Quản lý thay đổi cấu trúc |
| `receiptFileId` | String/ObjectId tùy kho file | Tham chiếu nội dung lớn nằm riêng |

Trong mongosh:

```javascript
db.orders.insertOne({
  _id: new ObjectId(),
  schemaVersion: NumberInt(2),
  orderId: "ORD-1001",
  customerId: "U42",
  total: NumberDecimal("259.90"),
  currency: "USD",
  createdAt: ISODate("2026-11-14T08:30:00Z"),
  itemCount: NumberInt(2),
  items: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(2),
      unitPrice: NumberDecimal("129.95")
    }
  ],
  receiptFileId: "receipt-ORD-1001"
});
```

Truy vấn theo thời gian và khách hàng:

```javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1
});

db.orders.find({
  customerId: "U42",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(20);
```

Tài liệu này tập trung vào **kiểu dữ liệu**. Các ràng buộc quan trọng khác như tính nhất quán của `total` so với tổng các mặt hàng, chống thanh toán trùng và bảo toàn trạng thái đơn vẫn cần được thiết kế bằng giao dịch/kiểm tra nghiệp vụ phù hợp.

### 17.1. API JSON nên hiển thị gì?

Một API có thể dùng JSON dễ đọc:

```json
{
  "orderId": "ORD-1001",
  "total": "259.90",
  "currency": "USD",
  "createdAt": "2026-11-14T08:30:00Z",
  "itemCount": 2
}
```

Ở đây `total` là string **theo hợp đồng API**, giúp giữ chính xác phần chữ số khi đi qua nhiều nền tảng; lớp ứng dụng chuyển sang `BigDecimal` và driver chuyển sang Decimal128. `createdAt` là string ISO 8601 **ở API**, nhưng lưu kiểu BSON Date trong database. Hai lớp không buộc phải có cùng định dạng, miễn ánh xạ được định nghĩa rõ và nhất quán.

Nếu chọn trả `total` dưới dạng JSON number, vẫn phải làm rõ độ chính xác và cách parser ở từng client hoạt động. Không có một cách duy nhất tốt nhất cho mọi API; tiêu chí là giữ ý nghĩa và khả năng chuyển đổi mà nghiệp vụ cần.

## 18. Các hiểu lầm thường gặp

**“Document database lưu JSON nên mọi trường đều có sáu kiểu JSON.”** Không đúng với hệ có BSON hoặc tập kiểu khác. MongoDB có Int32, Int64, Decimal128, ObjectId, Date, Binary và nhiều kiểu riêng.

**“BSON luôn ít byte hơn JSON vì là binary.”** Không đúng. BSON chứa thông tin kiểu và cấu trúc, có thể lớn hơn hoặc nhỏ hơn tùy dữ liệu. Nén là cơ chế riêng.

**“Chỉ cần chuỗi ngày dạng ISO là database hiểu thành Date.”** Không. String và BSON Date khác kiểu; cần codec hoặc chuyển đổi rõ ràng.

**“JSON number biểu diễn chính xác mọi số nguyên 64 bit.”** Không. Cú pháp JSON cho phép viết số lớn, nhưng parser như JavaScript Number có thể mất độ chính xác.

**“ObjectId là string gồm 24 ký tự hex.”** Không. Chuỗi hex là cách biểu diễn của định danh BSON 12 byte; so khớp theo kiểu trong database cần dùng giá trị ObjectId.

**“Decimal128 giống Double, chỉ nhiều byte hơn.”** Không. Decimal128 dùng biểu diễn số thực thập phân, nhằm giữ nhiều giá trị thập phân theo độ chính xác hữu hạn, còn Double là số thực nhị phân.

**“Có trường null tương đương thiếu trường.”** Không ở mức cấu trúc document. Một số truy vấn có thể gộp chúng theo ngữ nghĩa riêng; nghiệp vụ cần phân biệt.

**“Thư viện JSON nào cũng tự hiểu Extended JSON.”** Không. Parser JSON thường đọc các wrapper `$oid` hoặc `$date` như object thông thường; cần bộ giải mã EJSON phù hợp để khôi phục kiểu BSON.

**“Định dạng serialization quyết định khả năng truy vấn.”** Chỉ một phần. Index, mô hình dữ liệu, storage engine, API truy vấn, cách phân mảnh và ràng buộc nhất quán mới quyết định khả năng truy vấn thực tế.

## 19. Bài tập vận dụng

### Bài tập 1 — Phân loại kiểu

Xem JSON:

```json
{
  "id": "507f1f77bcf86cd799439011",
  "count": 12,
  "amount": "199.90",
  "createdAt": "2026-11-14T08:30:00Z",
  "attachment": "AAECAw==",
  "tags": ["new", "sale"]
}
```

**Câu hỏi:** JSON parser có tự nhận biết `id` là ObjectId, `amount` là Decimal128, `createdAt` là Date hay `attachment` là Binary không?

**Gợi ý:** Không. Đây lần lượt là string ở lớp JSON; `count` là JSON number, `tags` là array. Muốn khôi phục kiểu BSON, phải có hợp đồng ánh xạ và conversion/codec phù hợp.

### Bài tập 2 — Giá trị số lớn

Một API nhận:

```json
{
  "externalId": 9007199254740993
}
```

Ứng dụng JavaScript parse bằng `JSON.parse` rồi gửi ngược lại.

**Câu hỏi:** Có nguy cơ nào, và nên thiết kế hợp đồng thế nào?

**Gợi ý:** Có thể mất chính xác số nguyên lớn vì vượt giới hạn an toàn của `Number`. Nên dùng string định danh hoặc phương án serialization/typed parser bảo toàn Int64 trước khi chuyển thành kiểu phù hợp tại database.

### Bài tập 3 — Truy vấn theo thời gian

Collection có hai document:

```javascript
{ _id: 1, createdAt: "2026-11-14T08:30:00Z" }
{ _id: 2, createdAt: ISODate("2026-11-14T08:30:00Z") }
```

**Câu hỏi:** Tại sao cùng một câu truy vấn lọc `createdAt >= ISODate(...)` có thể xử lý khác nhau?

**Gợi ý:** Một document chứa string, một document chứa BSON Date. Các bộ so sánh và điều kiện truy vấn phân biệt kiểu; cần chuẩn hóa và migrate dữ liệu.

### Bài tập 4 — Null và missing

Cho:

```javascript
{ _id: 1, email: null }
{ _id: 2 }
{ _id: 3, email: "" }
```

**Câu hỏi:** Làm sao tìm chỉ những document **không có trường `email`** trong MongoDB?

**Gợi ý:**

```javascript
db.users.find({ email: { $exists: false } });
```

### Bài tập 5 — Java và số tiền

Xem:

```java
BigDecimal a = new BigDecimal(0.1);
BigDecimal b = new BigDecimal("0.1");
```

**Câu hỏi:** Vì sao `b` thường phù hợp hơn khi bắt đầu từ giá trị thập phân nghiệp vụ?

**Gợi ý:** `a` xây từ giá trị Double đã xấp xỉ `0.1`; `b` xây trực tiếp từ chuỗi thập phân. Khi ghi BSON, có thể chuyển sang Decimal128 nếu phạm vi và độ chính xác phù hợp.

### Bài tập 6 — Chọn định dạng giữa các dịch vụ

Một dịch vụ Java ghi sự kiện ra queue; dịch vụ khác dùng JavaScript, dịch vụ thứ ba dùng Go. Sự kiện chứa UUID, số nguyên 64 bit, Decimal và thời điểm.

**Câu hỏi:** Các đội cần thống nhất những gì, bất kể chọn JSON, BSON, Avro hay Protobuf?

**Gợi ý:** Tên và ý nghĩa trường, kiểu số, độ chính xác, timezone/đơn vị thời gian, biểu diễn UUID/ID, null/missing, quy tắc thêm/xóa trường và phiên bản schema. Công nghệ serialization không tự thay thế hợp đồng dữ liệu.

## 20. Kết luận

Trong mô hình tài liệu, **JSON là định dạng văn bản linh hoạt và phổ biến**, còn **BSON là biểu diễn nhị phân có thêm nhiều kiểu dữ liệu đặc thù** như ObjectId, Int32, Int64, Decimal128, Date và Binary. Các định dạng khác như CBOR, MessagePack, Avro và Protobuf giải quyết những nhu cầu trao đổi hoặc ràng buộc schema riêng; chúng không tự quyết định hệ quản trị có thể truy vấn tài liệu ra sao.

Khi thiết kế document database, điều cần bảo đảm là **giá trị được hiểu đúng từ API, qua ứng dụng và driver, đến dữ liệu đã lưu**. Kiểu số phải giữ độ chính xác phù hợp; thời gian phải mang ngữ nghĩa rõ ràng; định danh phải đúng kiểu; null và missing phải được phân biệt; array và document lồng nhau phải được truy vấn đúng. Khi những quy tắc này được xác định từ đầu, tính linh hoạt của mô hình tài liệu trở thành lợi thế mà vẫn kiểm soát được dữ liệu qua nhiều phiên bản ứng dụng.
