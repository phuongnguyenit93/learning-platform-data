# Phân biệt JSON, BSON và Extended JSON trong MongoDB

Khi làm việc với MongoDB, cùng một document có thể được biểu diễn theo nhiều cách: dưới dạng văn bản JSON khi trao đổi qua API, dưới dạng BSON khi MongoDB lưu trữ và truyền dữ liệu, hoặc dưới dạng Extended JSON khi cần nhìn thấy các kiểu dữ liệu riêng của BSON trong một tài liệu văn bản. Ba khái niệm này liên quan chặt chẽ nhưng **không thể thay thế cho nhau trong mọi tình huống**.

Ví dụ, một mã định danh MongoDB có kiểu **ObjectId**, thời điểm có kiểu **Date** và số tiền có kiểu **Decimal128**. Nếu chỉ nhìn chúng như chuỗi và số JSON thông thường, bạn có thể đánh mất thông tin kiểu dữ liệu, sai lệch số có độ chính xác lớn hoặc thực hiện truy vấn không khớp với giá trị lưu trong database.

Bài học này giải thích từng định dạng, so sánh khả năng biểu diễn kiểu dữ liệu, phân biệt hai chế độ Extended JSON (Canonical và Relaxed), rồi thực hành chuyển đổi và nhận diện lỗi thường gặp.

## 1. Bức tranh tổng thể

Hãy xem ba dạng biểu diễn của cùng một ý tưởng:

~~~text
Ứng dụng / API / file cấu hình
          |
          | Văn bản JSON
          v
    {"name":"Bút", "quantity":5}

MongoDB Driver <------------------------> MongoDB Server
                 tài liệu BSON nhị phân
                       (có mã kiểu)
          |
          | Cần xem, xuất hoặc trao đổi dữ liệu BSON
          | dưới dạng văn bản mà vẫn biểu diễn được kiểu
          v
  Extended JSON
  {"quantity":{"$numberInt":"5"}}
~~~

Một cách phân biệt ngắn gọn:

| Tiêu chí | JSON | BSON | Extended JSON (EJSON) |
|---|---|---|---|
| Bản chất | Định dạng văn bản theo cú pháp JSON | Định dạng nhị phân có thông tin kiểu | Quy ước biểu diễn giá trị BSON bằng văn bản có cú pháp JSON |
| Dùng phổ biến | REST API, cấu hình, log, trao đổi dữ liệu | Document của MongoDB, giao tiếp driver–server | Xuất/nhập dữ liệu MongoDB, ví dụ tài liệu, kiểm tra dữ liệu có kiểu |
| Dễ đọc bằng mắt | Có | Không trực tiếp | Có, nhưng nhiều trường dạng wrapper |
| Kiểu cơ bản | object, array, string, number, boolean, null | Có các kiểu tương ứng, đồng thời có nhiều kiểu MongoDB | Dùng cú pháp JSON và wrapper để thể hiện kiểu BSON |
| ObjectId, Date, Decimal128 | Không có kiểu bản địa | Có kiểu bản địa | Có dạng biểu diễn riêng như $oid, $date, $numberDecimal |
| Phân biệt Int32, Int64, Double | Không có thẻ kiểu theo chuẩn JSON | Có | Canonical EJSON biểu diễn bằng wrapper riêng; Relaxed có thể dùng số JSON thường |
| Lưu trực tiếp như tệp dễ sửa | Có | Không thuận tiện | Có |
| Giữ chính xác mọi kiểu BSON khi chuyển đổi | Không tự bảo đảm | Có nếu được driver xử lý đúng | Canonical hướng đến giữ thông tin kiểu, trong giới hạn quy ước chuyển đổi và hỗ trợ của công cụ |

**Điểm cốt lõi:** JSON và Extended JSON đều có thể được ghi thành file văn bản; BSON là định dạng nhị phân. Extended JSON **không phải một kiểu lưu trữ nhị phân khác của MongoDB**; nó là cách viết các giá trị BSON để con người và các công cụ văn bản có thể trao đổi.

## 2. JSON: ngôn ngữ dữ liệu văn bản phổ biến

JSON (JavaScript Object Notation) là một định dạng trao đổi dữ liệu bằng văn bản. Một JSON value có thể là:

- **Object:** tập hợp các cặp tên trường và giá trị.
- **Array:** danh sách giá trị có thứ tự.
- **String:** chuỗi ký tự đặt trong dấu nháy kép.
- **Number:** số viết theo cú pháp JSON, không kèm nhãn kiểu Int32 hay Decimal128.
- **Boolean:** true hoặc false.
- **Null:** null.

Ví dụ JSON hợp lệ:

~~~json
{
  "orderId": "ORD-001",
  "customer": {
    "name": "Lan",
    "city": "Hà Nội"
  },
  "items": [
    {"sku": "PEN-01", "quantity": 2},
    {"sku": "BOOK-03", "quantity": 1}
  ],
  "total": 149900,
  "paid": false,
  "shippedAt": null
}
~~~

JSON phù hợp khi trao đổi với frontend, gửi HTTP request/response hoặc lưu cấu hình. Tuy nhiên, cách viết JSON **không chỉ ra số 149900 là Int32, Int64, Double hay Decimal128**. Bộ đọc JSON phải quyết định tạo kiểu số nào theo ngôn ngữ và thư viện sử dụng.

JSON chuẩn cũng không có kiểu ngày giờ hay mã định danh MongoDB. Trong nhiều API, ứng dụng chủ động quy ước:

~~~json
{
  "id": "66f1c2a4b1d2e3f405162738",
  "createdAt": "2026-01-15T08:30:00.000Z"
}
~~~

Ở cấp JSON, cả **id** và **createdAt** đều chỉ là chuỗi. Việc hiểu chuỗi thứ nhất là ObjectId, chuỗi thứ hai là thời điểm phải do ứng dụng, schema hoặc bộ chuyển đổi thực hiện.

### 2.1. JSON không phải cú pháp đối tượng JavaScript

Những biểu thức dưới đây thường xuất hiện trong JavaScript hoặc MongoDB Shell, nhưng **không phải JSON hợp lệ**:

~~~javascript
// JavaScript / mongosh, không phải JSON chuẩn
{
  name: "Lan",                         // tên trường chưa đặt trong dấu nháy kép
  createdAt: new Date(),               // biểu thức JavaScript
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  quantity: NumberLong("5"),           // lời gọi hàm
}
~~~

JSON yêu cầu tên trường được bao trong dấu nháy kép; JSON không hỗ trợ comment, lời gọi hàm hay dấu phẩy thừa ở cuối danh sách. Vì vậy, không thể lấy nguyên đoạn mã mongosh rồi giả định bộ đọc JSON sẽ hiểu.

Một giá trị số đặc biệt như NaN, Infinity hoặc -Infinity cũng không phải literal số hợp lệ của JSON chuẩn.

## 3. BSON: định dạng document nhị phân của MongoDB

BSON là viết tắt thường được diễn giải là **Binary JSON**. Đây là một định dạng mã hóa dữ liệu thành chuỗi byte, có mã kiểu cho từng giá trị. MongoDB sử dụng BSON để biểu diễn document trong quá trình lưu trữ và trao đổi qua giao thức MongoDB.

Đối với người lập trình, một document vẫn có thể được thao tác như object/map:

~~~javascript
{
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  name: "Bút",
  quantity: 5,
  createdAt: ISODate("2026-01-15T08:30:00.000Z")
}
~~~

Đây là **cách mongosh hiển thị hoặc tạo giá trị**, không phải byte BSON thật. Khi driver mã hóa document, nó ghi ra cấu trúc nhị phân. Với một document BSON thông thường, định dạng tổng quát có:

~~~text
Document BSON
  ├── Độ dài document (4 byte, little-endian)
  ├── Phần tử 1
  │     ├── Mã kiểu (1 byte)
  │     ├── Tên trường (chuỗi C kết thúc bằng byte 0)
  │     └── Giá trị được mã hóa theo kiểu
  ├── Phần tử 2
  │     └── ...
  └── Byte kết thúc document (0)
~~~

Thông tin kiểu nằm trong dữ liệu nhị phân, không phụ thuộc vào việc người đọc đoán định dạng của chuỗi hoặc số từ nội dung. Chẳng hạn, cùng giá trị toán học **5** có thể được mã hóa là Int32, Int64 hoặc Double với mã kiểu khác nhau.

### 3.1. Những kiểu BSON thường gặp

| Kiểu BSON | Ý nghĩa | Ví dụ hay gặp trong MongoDB |
|---|---|---|
| String | Chuỗi UTF-8 | Tên sản phẩm, email |
| Object / Embedded Document | Document lồng nhau | Địa chỉ, thông tin giao hàng |
| Array | Danh sách có thứ tự | Danh sách sản phẩm |
| Boolean | Đúng hoặc sai | isActive |
| Null | Giá trị null được lưu rõ ràng | middleName: null |
| Int32 | Số nguyên có dấu 32 bit | Số lượng, bộ đếm nhỏ |
| Int64 / Long | Số nguyên có dấu 64 bit | Bộ đếm lớn, mã số dạng số |
| Double | Số thực dấu phẩy động IEEE 754 double | Điểm số, đại lượng đo lường |
| Decimal128 | Số thập phân theo định dạng Decimal128 | Giá tiền cần kiểm soát độ chính xác thập phân |
| ObjectId | Định danh BSON 12 byte | _id mặc định thường gặp |
| Date | Số nguyên 64 bit biểu diễn mili giây từ Unix epoch | createdAt, updatedAt |
| Timestamp | Giá trị gồm thành phần giây và bộ tăng thứ tự; thường dùng trong ngữ cảnh nội bộ/replication | Thao tác liên quan oplog |
| Binary | Mảng byte kèm subtype | Hash, dữ liệu nhị phân |
| Regular Expression | Biểu thức chính quy và cờ tùy chọn | Điều kiện khớp pattern được lưu |
| MinKey / MaxKey | Giá trị đặc biệt phục vụ so sánh thứ tự BSON | Các trường hợp truy vấn/chỉ mục đặc biệt |

BSON còn có một số kiểu cũ hoặc chuyên biệt khác, như JavaScript Code hay Undefined đã bị hạn chế hoặc không còn được khuyến nghị trong nhiều trường hợp. Khi thiết kế ứng dụng mới, nên chọn những kiểu phổ biến được driver hỗ trợ rõ ràng.

### 3.2. BSON có phải luôn nhỏ hơn hoặc nhanh hơn JSON?

Không nhất thiết. BSON được thiết kế để máy đọc và phân biệt kiểu dễ dàng, nhưng mỗi document có thêm thông tin độ dài, mã kiểu và tên trường. Với dữ liệu nhỏ, file BSON **có thể lớn hơn** văn bản JSON tương ứng. Với kiểu số, kiểu nhị phân và việc phân tích cú pháp, chi phí xử lý lại khác nhau.

Không nên đánh đồng chữ "Binary" với "nén dữ liệu". BSON **không tự động là định dạng nén**, và hiệu quả bộ nhớ/lưu trữ còn phụ thuộc cách thiết kế schema, nén lưu trữ, kiểu dữ liệu, chỉ mục và workload.

MongoDB giới hạn kích thước một BSON document thông thường ở **16 MiB**. Đây là giới hạn document của MongoDB, không phải một quy tắc chung của mọi file JSON.

## 4. Extended JSON: viết các kiểu BSON bằng cú pháp JSON

Extended JSON (thường viết tắt là **EJSON**) định nghĩa cách thể hiện các giá trị BSON qua những object đặc biệt trong JSON. Một giá trị ObjectId không bị hạ thành chuỗi trần; nó có thể được viết thành:

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  }
}
~~~

Một parser JSON thông thường vẫn đọc được văn bản trên. Nhưng nó chỉ tạo một object có khóa **$oid**; để khôi phục một ObjectId thực sự cần **bộ đọc Extended JSON** hiểu quy ước $oid.

Tương tự:

~~~json
{
  "createdAt": {
    "$date": "2026-01-15T08:30:00.000Z"
  },
  "amount": {
    "$numberDecimal": "149900.50"
  }
}
~~~

Các wrapper **$date** và **$numberDecimal** mang ý nghĩa kiểu dữ liệu. Đây là lý do EJSON hữu ích khi xuất document ra văn bản hoặc thử nghiệm các ca dữ liệu cần giữ kiểu.

**Điều quan trọng:** Extended JSON là một quy ước trên nền cú pháp JSON, không phải bộ toán tử truy vấn MongoDB. Ví dụ object {"$oid":"..."} không tự động có nghĩa là ObjectId khi bạn đưa nó như một JavaScript object vào hàm truy vấn. Muốn sử dụng như ObjectId, hãy tạo ObjectId hoặc giải mã bằng EJSON parser của driver.

### 4.1. Hai chế độ Extended JSON v2

Đối với Extended JSON v2, hai cách trình bày thường gặp là:

1. **Canonical Extended JSON:** dùng biểu diễn tường minh cho các kiểu BSON, nhất là các kiểu số. Phù hợp khi cần trao đổi có kiểm soát hoặc giữ chính xác thông tin kiểu khi chuyển đổi qua văn bản.
2. **Relaxed Extended JSON:** ưu tiên dễ đọc, dùng các số JSON thông thường khi có thể và vẫn giữ wrapper cho những kiểu mà JSON không biểu diễn trực tiếp, như ObjectId và Decimal128. Phù hợp cho việc đọc, log hoặc trao đổi gần với JSON thông thường.

Đây là hai **chế độ biểu diễn của cùng hệ Extended JSON**, không phải hai kiểu database hay hai định dạng lưu trên đĩa khác nhau.

## 5. Canonical và Relaxed: so sánh trên một document

Giả sử MongoDB có document với các kiểu BSON:

- _id: ObjectId
- title: String
- quantity: Int32
- total: Decimal128
- createdAt: Date
- active: Boolean

### 5.1. Canonical Extended JSON

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  },
  "title": "Sổ tay",
  "quantity": {
    "$numberInt": "12"
  },
  "total": {
    "$numberDecimal": "249.90"
  },
  "createdAt": {
    "$date": {
      "$numberLong": "1735689600000"
    }
  },
  "active": true
}
~~~

Ở đây:

- **$numberInt** khẳng định quantity mang kiểu BSON Int32, thay vì chỉ là một JSON number mơ hồ.
- **$numberDecimal** giữ kiểu Decimal128 và biểu diễn thập phân dạng chuỗi.
- **$date** bao **$numberLong** ghi số mili giây kể từ 1970-01-01T00:00:00Z, là cách biểu diễn Canonical của BSON Date.
- **$oid** mô tả ObjectId bằng 24 ký tự hex, tương ứng 12 byte.

### 5.2. Relaxed Extended JSON

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  },
  "title": "Sổ tay",
  "quantity": 12,
  "total": {
    "$numberDecimal": "249.90"
  },
  "createdAt": {
    "$date": "2025-01-01T00:00:00Z"
  },
  "active": true
}
~~~

Hai ví dụ mô tả cùng các **giá trị**; cách trình bày số nguyên và ngày khác nhau. Relaxed dễ đọc hơn, nhưng một số thông tin kiểu số có thể không được thể hiện đủ để phân biệt Int32, Int64 và Double khi chuyển qua môi trường khác.

Ví dụ, chỉ nhìn:

~~~json
{"score": 12}
~~~

Bạn không thể chắc chắn giá trị BSON ban đầu là Int32(12), Int64(12) hay Double(12). Một thư viện có thể chọn Int32 theo khoảng giá trị; thư viện khác có thể tạo Number kiểu double. Nếu **giữ nguyên kiểu gốc** là yêu cầu bắt buộc, hãy sử dụng Canonical Extended JSON và bộ chuyển đổi hỗ trợ đúng chuẩn.

### 5.3. Bảng chuyển đổi những kiểu BSON thông dụng

| BSON | Canonical Extended JSON | Relaxed Extended JSON |
|---|---|---|
| Int32 bằng 42 | {"$numberInt":"42"} | 42 |
| Int64 bằng 42 | {"$numberLong":"42"} | Có thể là 42 nếu biểu diễn an toàn theo quy tắc relaxed |
| Int64 lớn hơn giới hạn số nguyên an toàn của JavaScript | {"$numberLong":"9007199254740993"} | Cần wrapper số nguyên dài để không mất chính xác |
| Double bằng 3.5 | {"$numberDouble":"3.5"} | 3.5 |
| Decimal128 bằng 19.90 | {"$numberDecimal":"19.90"} | {"$numberDecimal":"19.90"} |
| ObjectId | {"$oid":"66f1c2a4b1d2e3f405162738"} | Giống Canonical |
| Date (thời điểm UTC thông thường) | {"$date":{"$numberLong":"1735689600000"}} | {"$date":"2025-01-01T00:00:00Z"} |
| Binary ba byte 01 02 03, subtype 00 | {"$binary":{"base64":"AQID","subType":"00"}} | Giống Canonical |
| Regular Expression | {"$regularExpression":{"pattern":"^A","options":"i"}} | Giống Canonical |
| Timestamp | {"$timestamp":{"t":1710000000,"i":1}} | Giống Canonical |
| MinKey | {"$minKey":1} | Giống Canonical |
| MaxKey | {"$maxKey":1} | Giống Canonical |

Đây là các mẫu tiêu biểu của **Extended JSON v2**. Một số dữ liệu đặc biệt như giá trị Double NaN/Infinity, giá trị Date ngoài khoảng được hỗ trợ bởi biểu diễn ISO thuận tiện, hay kiểu cũ có quy tắc riêng; vì vậy không nên tự viết bộ phân tích EJSON bằng cách dự đoán từ vài ví dụ.

### 5.4. Những gì vẫn giữ nguyên ở cả ba cách nhìn

String, Boolean, Null, Array và embedded document nhìn gần giống nhau:

~~~json
{
  "name": "An",
  "active": true,
  "tags": ["mongodb", "bson"],
  "profile": {
    "city": "Đà Nẵng",
    "verified": null
  }
}
~~~

Không phải **mọi trường** đều cần một wrapper EJSON. Wrapper xuất hiện khi cần mang hoặc làm rõ thông tin kiểu mà JSON cơ bản không có.

## 6. Cạm bẫy lớn nhất: độ chính xác và loại số

Trong JSON chuẩn, cú pháp số cho phép viết:

~~~json
{
  "small": 7,
  "big": 9007199254740993,
  "price": 19.90
}
~~~

Nhưng cách lưu các số sau khi parse **phụ thuộc ngôn ngữ và thư viện**. Trong JavaScript, kiểu Number dùng IEEE 754 double; các số nguyên chỉ được bảo toàn chính xác trong khoảng từ **-(2^53 - 1)** đến **2^53 - 1**. Nếu chuyển một Int64 lớn thành JavaScript Number, dữ liệu có thể bị làm tròn.

Ví dụ:

~~~javascript
// 9007199254740993 vượt giới hạn số nguyên an toàn của Number.
const unsafe = 9007199254740993;
console.log(Number.isSafeInteger(unsafe)); // false

// Chuỗi vẫn giữ nguyên chữ số; driver cần tạo kiểu Long/BSON tương ứng.
const exactText = "9007199254740993";
~~~

JSON có thể ghi dãy chữ số đó, nhưng **JSON.parse trong JavaScript** thường đưa nó vào Number và có thể mất chính xác. Vì vậy, một Int64 giá trị lớn nên được biểu diễn dưới dạng Extended JSON:

~~~json
{
  "visits": {
    "$numberLong": "9007199254740993"
  }
}
~~~

Một trình EJSON tương thích sẽ hiểu đây là số nguyên 64 bit và tránh bước parse thuần Number làm mất chữ số. Khi xử lý tiếp, cần dùng kiểu số nguyên phù hợp (ví dụ Long hoặc BigInt tùy driver và tùy cấu hình) thay vì ép về Number.

### 6.1. Double không đồng nghĩa với Decimal128

Double lưu số theo dạng nhị phân dấu phẩy động. Nhiều phân số thập phân, ví dụ 0.1, không có biểu diễn hữu hạn chính xác ở hệ nhị phân:

~~~javascript
console.log(0.1 + 0.2 === 0.3); // false trong JavaScript Number
~~~

BSON **Decimal128** phục vụ các phép tính thập phân cần độ chính xác phù hợp, chẳng hạn giá tiền hoặc dữ liệu tài chính trong giới hạn của định dạng Decimal128. Trong EJSON:

~~~json
{
  "unitPrice": {
    "$numberDecimal": "0.10"
  },
  "tax": {
    "$numberDecimal": "0.20"
  }
}
~~~

Giữ phần giá trị dưới dạng chuỗi trong wrapper là cách để thư viện tạo Decimal128 mà không đi qua một Number kém chính xác. Khi cộng/trừ trong MongoDB, vẫn cần chọn toán tử, quy tắc làm tròn và xử lý tỉ lệ thập phân phù hợp nghiệp vụ; Decimal128 không tự thay thế thiết kế quy tắc tiền tệ.

### 6.2. Tại sao 5, 5.0 và "5" không phải một kiểu?

- **5** trong JSON là number; sau parse chưa xác định rõ kiểu BSON gốc.
- **5.0** là biểu diễn dạng số JSON; khi parse, thư viện có thể không giữ được dấu .0 như một thông tin kiểu.
- **"5"** là string; MongoDB không tự coi đó là một BSON number.
- **{"$numberInt":"5"}** trong Canonical EJSON mô tả Int32.
- **{"$numberLong":"5"}** trong Canonical EJSON mô tả Int64.
- **{"$numberDouble":"5.0"}** trong Canonical EJSON mô tả Double.

Phân biệt **giá trị toán học** và **kiểu biểu diễn** là kiến thức nền tảng khi đọc dữ liệu MongoDB hoặc kiểm tra document có thay đổi kiểu sau khi import/export.

## 7. ObjectId, Date, Timestamp và Binary

### 7.1. ObjectId là kiểu BSON, không chỉ là chuỗi hex

ObjectId thông thường có **12 byte** dữ liệu; chuỗi hex gồm **24 ký tự** là cách ghi dễ nhìn:

~~~javascript
// Mongosh
const id = ObjectId("66f1c2a4b1d2e3f405162738");
db.customers.findOne({ _id: id });
~~~

Trong Extended JSON:

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  }
}
~~~

Còn trong JSON thường:

~~~json
{
  "_id": "66f1c2a4b1d2e3f405162738"
}
~~~

Hai document sau **không tương đương về kiểu _id**: document thứ nhất chứa ObjectId, document thứ hai chứa String. Nếu _id lưu là ObjectId, truy vấn bằng chuỗi hex chưa được chuyển kiểu sẽ không khớp chỉ vì hai cách hiển thị giống nhau.

MongoDB có thể dùng _id kiểu khác (ví dụ string), nếu ứng dụng chủ động chọn. Vì thế không nên ép mọi chuỗi id thành ObjectId khi chưa biết schema.

### 7.2. BSON Date là một thời điểm, không lưu chuỗi múi giờ

BSON Date lưu **số mili giây từ Unix epoch** trong một số nguyên 64 bit. Thời điểm này độc lập với cách bạn định dạng hiển thị theo múi giờ.

Ví dụ cùng một thời điểm:

~~~json
{
  "canonical": {
    "$date": {
      "$numberLong": "1735689600000"
    }
  },
  "relaxed": {
    "$date": "2025-01-01T00:00:00Z"
  }
}
~~~

Hai trường minh họa hai cách viết, không phải yêu cầu phải lưu đồng thời cả hai trong một document thực tế. Chữ **Z** chỉ thời điểm UTC; khi hiển thị cho người dùng ở múi giờ Việt Nam (UTC+07:00), thời gian địa phương tương ứng sẽ là **07:00:00 ngày 01/01/2025**.

Trái lại:

~~~json
{
  "createdAt": "2025-01-01T00:00:00Z"
}
~~~

Đây chỉ là JSON string. Nếu gửi vào MongoDB mà không chuyển thành Date, trường đó sẽ được lưu thành BSON String, gây khác biệt khi truy vấn theo thời điểm, tính toán ngày hoặc lập index theo kiểu dữ liệu dự kiến.

### 7.3. Timestamp khác Date

MongoDB BSON Timestamp có hai thành phần **t** (giây) và **i** (bộ tăng). Nó thường gặp trong các cơ chế nội bộ như replication/oplog:

~~~json
{
  "ts": {
    "$timestamp": {
      "t": 1710000000,
      "i": 1
    }
  }
}
~~~

Timestamp **không phải** kiểu mặc định nên dùng để ghi ngày tạo đơn hàng. Trong nghiệp vụ, BSON Date thường phù hợp hơn để lưu một thời điểm.

### 7.4. Binary chứa byte và subtype

Ví dụ Extended JSON của ba byte 0x01, 0x02, 0x03:

~~~json
{
  "payload": {
    "$binary": {
      "base64": "AQID",
      "subType": "00"
    }
  }
}
~~~

**base64** mã hóa dữ liệu byte thành ký tự để đặt trong JSON; **subType** cho biết phân loại BSON Binary. Một JSON string chỉ chứa "AQID" không mang theo thông tin rằng nó là binary subtype 00.

## 8. Thực hành chuyển đổi với thư viện BSON trong JavaScript

Để thấy khác biệt mà không cần tự giải mã byte BSON, có thể dùng package **bson** của hệ sinh thái MongoDB Node.js. Ví dụ minh họa dùng cú pháp Node.js ES Modules; dự án cần cài package bson:

~~~bash
npm install bson
~~~

Tạo file **ejson-demo.mjs**:

~~~javascript
import {
  EJSON,
  ObjectId,
  Int32,
  Long,
  Decimal128
} from "bson";

const document = {
  _id: new ObjectId("66f1c2a4b1d2e3f405162738"),
  product: "Bàn phím",
  quantity: new Int32(5),
  largeCounter: Long.fromString("9007199254740993"),
  price: Decimal128.fromString("199.90"),
  createdAt: new Date("2026-01-15T08:30:00.000Z"),
  active: true,
  tags: ["mongo", "ejson"]
};

const canonical = EJSON.stringify(
  document,
  null,
  2,
  { relaxed: false }
);

const relaxed = EJSON.stringify(
  document,
  null,
  2,
  { relaxed: true }
);

console.log("CANONICAL EJSON:\n", canonical);
console.log("RELAXED EJSON:\n", relaxed);

// Parser EJSON tái tạo các đối tượng/kiểu BSON tương ứng.
const restored = EJSON.parse(canonical, { relaxed: false });
console.log("ObjectId:", restored._id instanceof ObjectId);
console.log("Int64:", restored.largeCounter.toString());
console.log("Decimal128:", restored.price.toString());
console.log("Date:", restored.createdAt.toISOString());
~~~

Chạy:

~~~bash
node ejson-demo.mjs
~~~

Quan sát trong phần Canonical:

- **quantity** được bọc bằng $numberInt.
- **largeCounter** được bọc bằng $numberLong với giá trị chữ số đầy đủ.
- **price** được bọc bằng $numberDecimal.
- **createdAt** được biểu diễn bằng $date chứa $numberLong.
- **_id** được biểu diễn bằng $oid.

Ở phần Relaxed, quantity thường dễ đọc hơn vì được xuất thành số JSON thông thường, trong khi ObjectId và Decimal128 vẫn cần wrapper. Với số nguyên 64 bit vượt miền an toàn của Number, thư viện EJSON sẽ ưu tiên cách bảo toàn giá trị phù hợp.

**Vì sao không dùng JSON.stringify thay cho EJSON.stringify?** Một JSON serializer thông thường không có nghĩa vụ giữ toàn bộ kiểu BSON. Một vài lớp của driver có thể tự cung cấp phương thức chuyển đổi JSON, nhưng chi tiết đó phụ thuộc thư viện; không nên xem JSON.stringify là hợp đồng bảo toàn kiểu BSON khi trao đổi giữa hệ thống.

### 8.1. Chuyển đổi đúng hướng

~~~text
BSON value trong ứng dụng
    |
    | EJSON.stringify(..., { relaxed: false })
    v
Canonical Extended JSON (chuỗi văn bản)
    |
    | EJSON.parse(..., { relaxed: false })
    v
BSON-aware objects trong ứng dụng
    |
    | Driver serialize
    v
BSON bytes gửi tới MongoDB
~~~

Đừng nhầm thao tác **EJSON.parse** với **JSON.parse**. Cả hai nhận văn bản có cú pháp JSON, nhưng chỉ EJSON parser hiểu các wrapper kiểu BSON để khôi phục kiểu tương ứng.

### 8.2. Khi viết Java/Spring Data MongoDB

Ứng dụng Java có thể thao tác các kiểu driver tương ứng, ví dụ:

~~~java
import java.time.Instant;
import java.util.Date;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;
import java.math.BigDecimal;

Document product = new Document()
        .append("_id", new ObjectId("66f1c2a4b1d2e3f405162738"))
        .append("name", "Bàn phím")
        .append("quantity", 5)
        .append("price", new Decimal128(new BigDecimal("199.90")))
        .append("createdAt", Date.from(Instant.parse("2026-01-15T08:30:00Z")));
~~~

Ví dụ này dùng các lớp BSON và Java MongoDB driver; bản thân code Java **không phải văn bản JSON**. Khi driver gửi document tới MongoDB, các giá trị được serialize sang BSON theo kiểu mà codec xác định. Nếu nhận dữ liệu từ một JSON REST API, ứng dụng cần ánh xạ và kiểm tra đầu vào trước khi tạo ObjectId, Date, Decimal128.

## 9. MongoDB Shell, driver, API và công cụ export

Trong thực tế, bạn sẽ thấy những dạng dữ liệu khác nhau tùy công cụ.

### 9.1. mongosh hiển thị dạng thân thiện, không phải file JSON chuẩn

~~~javascript
// MongoDB Shell (mongosh)
use shop

db.products.insertOne({
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  name: "Bàn phím",
  quantity: NumberInt(5),
  price: NumberDecimal("199.90"),
  createdAt: ISODate("2026-01-15T08:30:00Z")
});

db.products.findOne({
  _id: ObjectId("66f1c2a4b1d2e3f405162738")
});
~~~

**ObjectId(), NumberInt(), NumberDecimal() và ISODate() là helper/cú pháp của mongosh**, không phải cú pháp JSON. Khi driver gửi dữ liệu, những đối tượng có kiểu được chuyển sang BSON.

Nếu bạn có Canonical Extended JSON dưới dạng văn bản, hãy dùng EJSON parser hoặc công cụ nhập tương thích để khôi phục kiểu trước khi tạo truy vấn. Không lấy trực tiếp:

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  }
}
~~~

rồi giả định đó là filter chứa ObjectId khi truyền như object bình thường; lúc đó **$oid** vẫn chỉ là tên trường trong object cho đến khi được giải mã theo EJSON.

### 9.2. Ứng dụng REST API nên chọn hợp đồng dữ liệu rõ ràng

Một API có thể trả về dạng JSON đơn giản:

~~~json
{
  "id": "66f1c2a4b1d2e3f405162738",
  "price": "199.90",
  "createdAt": "2026-01-15T08:30:00Z"
}
~~~

Đây là lựa chọn **thiết kế API**: id và price được quy ước là chuỗi, createdAt là chuỗi thời điểm ISO-8601. API phải mô tả cách parse, validate và chuyển đổi khi lưu vào MongoDB. Một API khác có thể chọn EJSON với wrapper kiểu BSON nếu phục vụ công cụ quản trị hoặc trao đổi dữ liệu cần giữ nguyên kiểu.

Với API hướng đến frontend thông thường, không nhất thiết bắt khách hàng phải hiểu $oid hay $numberDecimal. Vấn đề cần giải quyết là **hợp đồng kiểu dữ liệu nhất quán**, chứ không phải mọi API đều phải trả Extended JSON.

### 9.3. mongoexport/mongoimport và mongodump/mongorestore

Hai cặp công cụ xử lý dữ liệu theo mục tiêu khác nhau:

| Công cụ | Dùng để làm gì | Dạng dữ liệu chính |
|---|---|---|
| mongoexport | Xuất collection để trao đổi qua file văn bản | JSON/Extended JSON hoặc CSV tùy tham số |
| mongoimport | Nhập dữ liệu từ JSON/Extended JSON hoặc CSV phù hợp | Đọc văn bản và tạo document trong MongoDB |
| mongodump | Tạo bản dump dữ liệu phục vụ sao lưu/di chuyển | BSON dump và metadata tương ứng |
| mongorestore | Khôi phục dữ liệu từ mongodump | Đọc BSON dump để tái tạo collection/index theo khả năng công cụ |

Ví dụ minh họa xuất dữ liệu bằng Extended JSON Canonical:

~~~bash
mongoexport --uri="mongodb://localhost:27017" --db=shop --collection=products --jsonFormat=canonical --out=products.json
~~~

Lệnh minh họa giả định bạn đã có một MongoDB truy cập được tại địa chỉ đó và có quyền xuất collection. Nếu MongoDB bật xác thực, cấu hình URI và phương thức cung cấp thông tin đăng nhập phù hợp; tránh ghi mật khẩu thật vào lịch sử terminal.

Với chế độ xuất JSON mặc định thông thường, mỗi document có thể nằm trên **một dòng JSON riêng** (JSON Lines), chứ không nhất thiết là một JSON array bao toàn bộ file. Khi đọc bằng ứng dụng ngoài, hãy kiểm tra cách công cụ xuất tổ chức các dòng.

Đối với **backup/restore đúng nghĩa**, mongodump/mongorestore thường phù hợp hơn mongoexport/mongoimport vì giữ dữ liệu BSON và metadata phục vụ khôi phục theo thiết kế công cụ. Tuy vậy, chiến lược backup của hệ thống thật còn phải đáp ứng yêu cầu nhất quán, downtime, phục hồi và kiểm tra restore.

## 10. Những nhầm lẫn thường gây lỗi

| Nhầm lẫn | Hậu quả | Cách hiểu và xử lý |
|---|---|---|
| JSON và BSON là một | Không hiểu vì sao MongoDB cần loại dữ liệu riêng | JSON là văn bản; BSON là định dạng nhị phân có thông tin kiểu. |
| BSON luôn nhỏ hơn JSON | Ước lượng sai dung lượng | BSON có thêm overhead; kích thước phụ thuộc dữ liệu cụ thể. |
| Một chuỗi hex 24 ký tự luôn là ObjectId | Query _id có thể không khớp | Kiểm tra kiểu _id thật; chỉ chuyển sang ObjectId nếu schema yêu cầu. |
| Chuỗi thời gian ISO luôn được MongoDB lưu thành Date | So sánh/sắp xếp và truy vấn có thể sai ngữ nghĩa | Parse chuỗi thành kiểu Date trước khi ghi hoặc chọn String theo schema có chủ ý. |
| Số JSON luôn được giữ chính xác ở mọi môi trường | Int64 lớn bị làm tròn | Dùng Long/Decimal128 và Canonical EJSON hoặc hợp đồng truyền số bằng string khi cần. |
| Số 19.90 kiểu Double tương đương Decimal128 | Mất ngữ nghĩa kiểu và độ chính xác thập phân | Dùng Decimal128 cho dữ liệu cần tính thập phân chính xác. |
| JSON.parse tự hiểu $oid, $date | Nhận object thường thay vì ObjectId/Date | Dùng EJSON.parse hoặc ánh xạ sang BSON type rõ ràng. |
| Canonical và Relaxed là hai kiểu lưu database | Sai mô hình lưu trữ | Cả hai đều là cách biểu diễn văn bản của BSON. |
| Copy nguyên object mongosh vào file JSON | Parser JSON báo lỗi cú pháp | Dùng JSON/Extended JSON hợp lệ hoặc mã nguồn JavaScript tùy mục tiêu. |
| BSON Timestamp là BSON Date | Dùng sai loại dữ liệu thời gian | Timestamp phục vụ tình huống chuyên biệt; Date thường dùng cho thời điểm nghiệp vụ. |
| Wrapper EJSON có thể được gửi thẳng như filter BSON ở mọi API | Driver/server hiểu wrapper là object/toán tử khác | Dùng parser EJSON trước hoặc tạo giá trị bằng lớp BSON của driver. |

### 10.1. Phân biệt null, trường thiếu và giá trị kiểu khác

Ba document sau biểu diễn ba tình huống khác nhau:

~~~json
{"name":"An","age":null}
{"name":"An"}
{"name":"An","age":"null"}
~~~

Trong document thứ nhất, trường age tồn tại với giá trị BSON Null. Trong document thứ hai, trường age không tồn tại. Trong document thứ ba, age là String chứa chữ "null".

Một số điều kiện truy vấn MongoDB có thể xử lý null và field bị thiếu theo cách gần nhau; hãy sử dụng các toán tử như **$exists** hoặc kiểm tra kiểu khi cần phân biệt chính xác. Đây là vấn đề về ngữ nghĩa document, không được giải quyết bằng việc đổi JSON thành BSON hay EJSON.

### 10.2. Tránh tự diễn giải wrapper bắt đầu bằng dấu $

Khi nhìn thấy:

~~~json
{"value":{"$numberLong":"42"}}
~~~

đừng xóa wrapper bằng cách lấy chuỗi "42" rồi parse thành Number một cách tùy tiện. Đó là dữ liệu số nguyên dài cần được chuyển đúng kiểu. Tương tự, các trường tên **$oid**, **$date**, **$binary** mang ý nghĩa trong ngữ cảnh Extended JSON; việc parser thuần JSON nhận được object chưa có nghĩa là nó đã tạo BSON type tương ứng.

Không nên coi mọi object có khóa bắt đầu bằng dấu $ đều là Extended JSON. MongoDB còn dùng các tên toán tử như **$set**, **$in**, **$gt** trong câu truy vấn và cập nhật; các toán tử này có ngữ nghĩa riêng và không phải wrapper biểu diễn BSON type.

## 11. Bài thực hành nhận diện và chuyển đổi

### Bài 1: Xác định kiểu thực sự

Xem các giá trị:

~~~json
{
  "a": "2026-01-15T08:30:00Z",
  "b": {"$date":"2026-01-15T08:30:00Z"},
  "c": "66f1c2a4b1d2e3f405162738",
  "d": {"$oid":"66f1c2a4b1d2e3f405162738"},
  "e": 42,
  "f": {"$numberLong":"42"}
}
~~~

Yêu cầu: nếu giải mã theo Extended JSON v2, hãy nêu kiểu BSON của từng trường và giải thích vì sao **a** khác **b**, **c** khác **d**.

**Gợi ý:** a và c là String; b là Date, d là ObjectId; e là number theo cách parser/driver diễn giải giá trị thông thường; f chỉ rõ Int64. Đừng khẳng định e luôn là Int32 nếu chưa biết bộ đọc và cách chuyển sang BSON.

### Bài 2: Viết Canonical Extended JSON

Một bản ghi hàng hóa có các trường:

| Trường | BSON type yêu cầu | Giá trị |
|---|---|---|
| _id | ObjectId | 66f1c2a4b1d2e3f405162738 |
| sku | String | KB-01 |
| stock | Int32 | 10 |
| soldTotal | Int64 | 9007199254740993 |
| price | Decimal128 | 199.90 |
| createdAt | Date | 2025-01-01T00:00:00Z |

Hãy tạo document **Canonical Extended JSON**, sử dụng đúng $oid, $numberInt, $numberLong, $numberDecimal và $date chứa $numberLong.

**Đáp án tham khảo:**

~~~json
{
  "_id": {
    "$oid": "66f1c2a4b1d2e3f405162738"
  },
  "sku": "KB-01",
  "stock": {
    "$numberInt": "10"
  },
  "soldTotal": {
    "$numberLong": "9007199254740993"
  },
  "price": {
    "$numberDecimal": "199.90"
  },
  "createdAt": {
    "$date": {
      "$numberLong": "1735689600000"
    }
  }
}
~~~

### Bài 3: Phát hiện sai lệch khi import/export

Giả sử database lưu:

~~~text
_id        : ObjectId(...)
soldTotal  : Int64(9007199254740993)
createdAt  : BSON Date
~~~

Một chương trình xuất ra:

~~~json
{
  "_id": "66f1c2a4b1d2e3f405162738",
  "soldTotal": 9007199254740992,
  "createdAt": "2025-01-01T00:00:00Z"
}
~~~

Xác định ít nhất ba rủi ro:

1. _id từ ObjectId đã trở thành String.
2. soldTotal mất một đơn vị do làm tròn qua kiểu số không giữ được Int64 lớn.
3. createdAt từ BSON Date trở thành String nếu khi import không có bước chuyển kiểu.

Hãy đề xuất dùng Canonical Extended JSON với EJSON serializer/parser phù hợp cho quá trình round-trip dữ liệu BSON, hoặc định nghĩa schema API và chuyển đổi kiểu rõ ràng ở biên hệ thống.

### Bài 4: Lựa chọn định dạng theo nhu cầu

Với mỗi yêu cầu sau, hãy lựa chọn định dạng thích hợp và giải thích:

- Trả kết quả danh sách sản phẩm cho ứng dụng web có DTO rõ ràng: thường dùng **JSON** theo hợp đồng API.
- Gửi và nhận document giữa MongoDB driver và MongoDB server: **BSON**.
- Xuất document sang file văn bản và cần giữ Int32, Int64, Date, Decimal128: ưu tiên **Canonical Extended JSON**.
- Xem document trong file văn bản dễ đọc, vẫn cần hiển thị ObjectId và Date: **Relaxed Extended JSON** có thể thuận tiện.
- Tạo bản dump phục vụ khôi phục dữ liệu MongoDB: dùng **mongodump/mongorestore** và định dạng BSON dump theo công cụ.

## 12. Ghi nhớ khi thiết kế ứng dụng MongoDB

Khi đọc một document, hãy tách ba câu hỏi:

1. **Dữ liệu thực sự có kiểu gì trong MongoDB?** Ví dụ ObjectId, String, Int32, Int64, Double, Decimal128 hay Date.
2. **Dữ liệu đang được hiển thị/trao đổi theo định dạng nào?** Ví dụ JSON thuần, Canonical EJSON, Relaxed EJSON hoặc biểu thức của mongosh.
3. **Thành phần nào chịu trách nhiệm chuyển kiểu?** Ví dụ MongoDB driver, EJSON parser, lớp DTO, serializer REST hoặc công cụ import/export.

JSON thuận tiện để trao đổi văn bản; BSON cung cấp cấu trúc nhị phân và kiểu dữ liệu phong phú cho MongoDB; Extended JSON là cầu nối để mang những kiểu dữ liệu đó vào văn bản có cú pháp JSON. Việc chọn đúng định dạng và đúng bộ chuyển đổi giúp tránh mất độ chính xác số, sai lệch ngày giờ và truy vấn không khớp kiểu dữ liệu.
