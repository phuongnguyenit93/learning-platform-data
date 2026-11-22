# Kiểu số int32, int64, double và Decimal128 trong MongoDB

Trong BSON, một giá trị mang ý nghĩa “số” không chỉ có một kiểu duy nhất. MongoDB hỗ trợ bốn kiểu số thường dùng: **int32**, **int64 (long)**, **double** và **Decimal128**. Chúng khác nhau ở miền giá trị, cách biểu diễn, độ chính xác, dung lượng lưu trữ và cách ứng dụng thao tác với dữ liệu. Chọn sai kiểu có thể khiến số tiền bị sai vài đơn vị nhỏ, bộ đếm lớn mất chữ số hoặc ứng dụng vô tình chuyển số nguyên chính xác sang số thực gần đúng.

Bài học tập trung vào các kiểu số BSON, cách tạo và nhận diện chúng trong **mongosh**, hành vi so sánh/truy vấn/tính toán, cách chuyển đổi an toàn và cách ánh xạ sang Java.

## 1. BSON là gì và vì sao có nhiều kiểu số?

**BSON (Binary JSON)** là định dạng tài liệu nhị phân MongoDB sử dụng. Khác JSON thông thường chỉ có một kiểu cú pháp số, BSON gắn một **mã kiểu** cho từng giá trị. Vì vậy hai tài liệu có cùng giá trị số học nhưng kiểu BSON khác nhau vẫn lưu được độc lập:

~~~javascript
{ value: Int32(42) }
{ value: Long("42") }
{ value: Double(42) }
{ value: Decimal128("42") }
~~~

Các tài liệu trên đều diễn tả số 42; tuy nhiên ứng dụng và MongoDB có thể đọc được kiểu BSON khác nhau của từng trường.

| Kiểu BSON | Mã BSON | Bí danh dùng với `$type` | Dung lượng phần giá trị | Bản chất |
| --- | ---: | --- | ---: | --- |
| **int32** | 16 | `"int"` | 4 byte | Số nguyên có dấu 32 bit |
| **int64 / long** | 18 | `"long"` | 8 byte | Số nguyên có dấu 64 bit |
| **double** | 1 | `"double"` | 8 byte | Số thực dấu phẩy động nhị phân IEEE 754 64 bit |
| **Decimal128** | 19 | `"decimal"` | 16 byte | Số thực dấu phẩy động thập phân IEEE 754 decimal128 |

Dung lượng trong bảng chỉ tính **giá trị số**; một trường BSON còn có byte nhận diện kiểu, tên trường và phần phụ khác của tài liệu. Không nên dùng bảng này để suy ra kích thước toàn bộ document.

**Điểm phân biệt cốt lõi:** int32 và int64 lưu **số nguyên chính xác** trong phạm vi của chúng; double lưu **số thực gần đúng theo cơ số 2**; Decimal128 lưu **số thập phân với tối đa 34 chữ số có nghĩa**. Decimal128 có độ chính xác hữu hạn, vì vậy không phải dạng số học độ chính xác vô hạn.

## 2. So sánh miền giá trị và độ chính xác

| Tiêu chí | int32 | int64 (long) | double | Decimal128 |
| --- | --- | --- | --- | --- |
| Miền giá trị | −2.147.483.648 đến 2.147.483.647 | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Số hữu hạn có độ lớn tối đa khoảng 1,797 × 10³⁰⁸; có ±Infinity, NaN | Tối đa 34 chữ số có nghĩa, khoảng số mũ rất rộng; có thể biểu diễn NaN/Infinity |
| Chính xác | Mọi số nguyên trong miền | Mọi số nguyên trong miền | Khoảng 15–17 chữ số thập phân có nghĩa; không chính xác cho phần lớn phân số thập phân như 0,1 | Chính xác cho các giá trị thập phân biểu diễn được trong giới hạn 34 chữ số |
| Độ chính xác số nguyên | Toàn miền | Toàn miền | Liên tục chính xác từ −2⁵³ đến 2⁵³; lớn hơn có thể mất số nguyên lẻ | Số nguyên trong giới hạn 34 chữ số có nghĩa |
| Trường hợp dùng | Số lượng nhỏ, tuổi, trạng thái mã hóa bằng số, đếm nhỏ | Bộ đếm rất lớn, định danh số nguyên, kích thước tính bằng byte | Đo lường, tỷ lệ, thống kê chấp nhận sai số | Tiền tệ, thuế, đơn giá, tỷ lệ cần số học thập phân xác định |

### 2.1. int32: số nguyên 32 bit

Int32 là số nguyên **có dấu**. Giá trị lớn nhất là **2³¹ − 1**, giá trị nhỏ nhất là **−2³¹**.

Ví dụ phù hợp:

- Số sản phẩm trong một đơn hàng.
- Số lần retry còn lại.
- Mức độ ưu tiên nằm trong khoảng hữu hạn.
- Năm hoặc số lượng luôn được xác nhận không vượt miền int32.

Nếu hệ thống có thể tăng một bộ đếm vượt 2.147.483.647, cần xem xét int64 hoặc cách tính riêng. Tên trường **count** không có nghĩa cứ dùng int32 là đủ.

### 2.2. int64 (long): số nguyên 64 bit

Int64 mở rộng khoảng giá trị nhưng vẫn biểu diễn **chính xác từng số nguyên** trong miền của nó. Dùng khi giá trị có thể lớn hơn giới hạn int32: số lượt xem tích lũy, số byte lưu trữ, đồng hồ đếm hoặc định danh nguyên lớn.

JavaScript lại dùng **Number** kiểu double cho số thông thường. Vì vậy không được lấy độ lớn miền int64 để suy luận rằng mọi số int64 đều truyền an toàn qua biến Number. Ví dụ:

~~~javascript
// Chạy trong mongosh (JavaScript):
Number.MAX_SAFE_INTEGER;              // 9007199254740991
Number.isSafeInteger(9007199254740991); // true
Number.isSafeInteger(9007199254740993); // false

// Đúng: truyền chuỗi thập phân để giữ nguyên giá trị lớn.
const exactLong = Long("9007199254740993");

// Nguy hiểm: đối số Number đã bị làm tròn trước khi Long nhận nó.
const unsafeLong = Long(9007199254740993);
~~~

**Quy tắc:** khi ghi số nguyên 64 bit có khả năng vượt **Number.MAX_SAFE_INTEGER = 2⁵³ − 1**, hãy truyền qua **chuỗi** hoặc đối tượng **Long** của driver, thay vì đi qua JavaScript Number.

### 2.3. double: số thực nhị phân

Double phù hợp với phép tính khoa học, độ đo và số liệu mà sai số làm tròn được kiểm soát. Double lưu dấu, phần trị và số mũ theo cơ số 2. Vì **0,1** không biểu diễn hữu hạn trong cơ số 2, tính toán có thể cho kết quả bất ngờ:

~~~javascript
0.1 + 0.2;                // 0.30000000000000004
0.1 + 0.2 === 0.3;        // false
~~~

Đây là đặc tính của **IEEE 754 binary64**, không phải lỗi riêng của MongoDB. Giá trị đo nhiệt độ hoặc kết quả phân tích thống kê thường chấp nhận sai số rất nhỏ. Ngược lại, so sánh tiền thanh toán dựa vào phép cộng double có thể dẫn đến lỗi logic.

Số nguyên lớn cũng là rủi ro của double: vượt **2⁵³ − 1**, không phải mọi số nguyên liên tiếp đều còn phân biệt được. Một con số nhìn như “số nguyên” trong JSON hoặc JavaScript vẫn có thể được lưu thành double.

### 2.4. Decimal128: số thực thập phân 128 bit

Decimal128 dùng chuẩn **IEEE 754 decimal128**, biểu diễn số theo hệ thập phân với **34 chữ số có nghĩa** và miền số mũ theo đặc tả khoảng **−6143 đến +6144**. Các giá trị như **0,1**, **0,2**, **19,99** có thể được biểu diễn đúng theo thập phân khi số chữ số không vượt giới hạn.

Ví dụ thường dùng:

~~~javascript
Decimal128("0.1")
Decimal128("19.99")
Decimal128("12345678901234567890.01")
~~~

Cần truyền chuỗi để giữ nguyên ý định thập phân. Nếu tạo Decimal128 từ một số JavaScript đã bị làm tròn, kiểu đích không thể tự đoán lại giá trị gốc.

Decimal128 không phải lời giải cho mọi vấn đề tính toán: phép toán có kết quả hơn 34 chữ số có nghĩa vẫn phải làm tròn; giá trị vượt miền có thể gây lỗi hoặc vô cực tùy phép toán. Với tiền tệ, ứng dụng còn cần xác định **đơn vị**, **số chữ số sau dấu thập phân** và **quy tắc rounding** của nghiệp vụ.

## 3. Tạo và quan sát từng kiểu trong mongosh

### 3.1. Chuẩn bị collection minh họa

Các ví dụ sau chạy trong **mongosh** kết nối với một MongoDB đang hoạt động. Dùng collection riêng cho bài học để không ảnh hưởng dữ liệu khác:

~~~javascript
const lab = db.getSiblingDB("bson_numeric_lab");
lab.numeric_examples.drop();

lab.numeric_examples.insertMany([
  { _id: "int32",    value: Int32(42) },
  { _id: "int64",    value: Long("9007199254740993") },
  { _id: "double",   value: Double(0.1) },
  { _id: "decimal",  value: Decimal128("0.10") }
]);

lab.numeric_examples.find().sort({ _id: 1 }).toArray();
~~~

Các constructor được khuyến nghị trong **mongosh** là:

| Kiểu | Cách tạo tường minh | Cách gọi tên cũ vẫn thường gặp |
| --- | --- | --- |
| int32 | `Int32(42)` | `NumberInt(42)` |
| int64 | `Long("9007199254740993")` | `NumberLong("9007199254740993")` |
| double | `Double(0.1)` | — |
| Decimal128 | `Decimal128("0.10")` | `NumberDecimal("0.10")` |

**Lưu ý về mongosh so với mongo shell cũ:** trong mongosh hiện đại, số JavaScript vừa là số nguyên và nằm trong phạm vi int32 thường được ghi thành **Int32**; những số không biểu diễn như int32 thường được ghi thành **Double**. Shell **không tự động chọn int64** cho một số nguyên quá lớn. Legacy **mongo** shell từng mặc định ghi số thành double. Vì vậy hãy chọn constructor tường minh khi kiểu lưu trữ là một phần hợp đồng dữ liệu.

### 3.2. Kiểm tra kiểu đang được lưu

MongoDB có toán tử aggregation **`$type`**; nó trả về tên loại BSON thực tế của giá trị:

~~~javascript
lab.numeric_examples.aggregate([
  {
    $project: {
      _id: 1,
      value: 1,
      bsonType: { $type: "$value" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Giá trị **bsonType** mong đợi lần lượt là **decimal**, **double**, **int** và **long** tương ứng với các tài liệu trên.

Toán tử **`$type`** trong **find** cũng lọc theo kiểu:

~~~javascript
lab.numeric_examples.find({ value: { $type: "int" } });
lab.numeric_examples.find({ value: { $type: "long" } });
lab.numeric_examples.find({ value: { $type: "double" } });
lab.numeric_examples.find({ value: { $type: "decimal" } });

// Bí danh gộp cả bốn kiểu số BSON:
lab.numeric_examples.find({ value: { $type: "number" } });
~~~

Lựa chọn **`$type: "number"`** hữu ích khi muốn loại bỏ dữ liệu string, null, boolean nhưng chưa cần phân biệt các kiểu số. Với dữ liệu đã bị lưu sai kiểu, nên kiểm tra từng loại trước khi thiết kế migration.

## 4. Giá trị bằng nhau có đồng nghĩa kiểu bằng nhau?

MongoDB có khả năng **so sánh giá trị giữa các kiểu số BSON**. Khi hai số khác kiểu biểu diễn cùng giá trị toán học một cách chính xác, điều kiện bằng có thể khớp cả hai. Tuy nhiên **`$type`** vẫn phân biệt kiểu lưu trữ.

Tạo bốn tài liệu mang giá trị một:

~~~javascript
lab.numeric_equal.drop();
lab.numeric_equal.insertMany([
  { _id: "a", value: Int32(1) },
  { _id: "b", value: Long("1") },
  { _id: "c", value: Double(1) },
  { _id: "d", value: Decimal128("1.00") }
]);

// Tìm theo giá trị: có thể khớp cả bốn tài liệu.
lab.numeric_equal.find({ value: 1 }).toArray();

// Tìm riêng các tài liệu được lưu dưới dạng Decimal128.
lab.numeric_equal.find({ value: { $type: "decimal" } }).toArray();
~~~

Đối với phân số thập phân, **double** và **Decimal128** có thể không bằng nhau dù nhìn giống nhau ở dạng in ra, vì double lưu giá trị nhị phân gần đúng:

~~~javascript
lab.numeric_fraction.drop();
lab.numeric_fraction.insertMany([
  { _id: "double", value: Double(1.01) },
  { _id: "decimal", value: Decimal128("1.01") }
]);

lab.numeric_fraction.find({
  value: Double(1.01)
}).toArray();

// Không nên mặc định rằng tài liệu Decimal128("1.01")
// sẽ khớp với điều kiện Double(1.01).
~~~

Hệ quả: **so sánh bằng giá trị** và **kiểm tra đúng kiểu** là hai việc khác nhau. Nếu trường **price** phải luôn là Decimal128, điều kiện so sánh bình thường không đảm bảo mọi tài liệu được lưu đúng kiểu; cần quy ước ghi dữ liệu, schema validation và/hoặc kiểm tra bằng `$type`.

## 5. Tính toán: độ chính xác và tự nâng kiểu

### 5.1. So sánh phép cộng double và Decimal128

Thực hiện phép cộng **trên MongoDB** bằng aggregation, để toán hạng giữ nguyên BSON type:

~~~javascript
lab.numeric_examples.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      doubleSum: {
        $add: [Double(0.1), Double(0.2)]
      },
      decimalSum: {
        $add: [Decimal128("0.1"), Decimal128("0.2")]
      },
      doubleType: { $type: Double(0.1) },
      decimalType: { $type: Decimal128("0.1") }
    }
  }
]);
~~~

Bạn sẽ thấy kết quả double có thể hiển thị theo giá trị gần đúng của **0,30000000000000004**, còn phép cộng Decimal128 cho số thập phân **0,3** chính xác ở ví dụ này.

**Không nên thử phép cộng bằng toán tử JavaScript `+` trực tiếp trên hai object Decimal128** rồi xem đó là phép cộng thập phân MongoDB. Toán tử JavaScript hoạt động theo cơ chế ép kiểu của JavaScript; với phép toán mong muốn, hãy dùng aggregation MongoDB hoặc kiểu thập phân phù hợp của ngôn ngữ ứng dụng.

### 5.2. Quy tắc nâng kiểu của `$sum`

Với **`$sum`** trong aggregation, khi đầu vào trộn kiểu, MongoDB xét thứ tự tăng về phạm vi:

~~~text
int32 → int64 → double → Decimal128
~~~

Đây là quy tắc **xác định kiểu kết quả của phép cộng**, không đồng nghĩa mọi lần nâng kiểu đều giữ được độ chính xác tuyệt đối:

- Cộng các số **int32** vượt miền int32 có thể được nâng thành **int64**.
- Khi kết quả **int64** tràn miền, MongoDB có thể nâng thành **double**, đồng thời có nguy cơ mất độ chính xác số nguyên.
- Khi kết quả double hoặc Decimal128 vượt miền tương ứng, kết quả phép cộng có thể là **±Infinity**.
- Nếu trộn số double đã được làm tròn với decimal, việc nâng kiểu sau đó không tự khôi phục thông tin bị mất từ trước.

Ví dụ tính doanh thu bằng Decimal128:

~~~javascript
lab.orders.drop();
lab.orders.insertMany([
  { _id: 1, price: Decimal128("19.90") },
  { _id: 2, price: Decimal128("10.10") }
]);

lab.orders.aggregate([
  {
    $group: {
      _id: null,
      total: { $sum: "$price" },
      count: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      total: 1,
      count: 1,
      totalType: { $type: "$total" }
    }
  }
]);
~~~

Trường **total** có giá trị thập phân **30,00** và kiểu **decimal**. Kết quả hiển thị có thể khác về số chữ số 0 tận cùng, nhưng giá trị số học là 30.

Để duy trì quy tắc dữ liệu, tránh nhập **một phần giá bằng Decimal128, phần còn lại bằng double** rồi dựa vào việc MongoDB tự nâng kiểu. Tính tổng phải bắt đầu từ dữ liệu đã thống nhất đơn vị và kiểu.

### 5.3. Khi nào cần làm tròn?

Ngay cả Decimal128 cũng không thể tự quyết định tiền phải làm tròn tới hai chữ số hay bốn chữ số. Tùy nghiệp vụ, MongoDB có thể dùng **`$round`**, **`$trunc`** hoặc chương trình Java dùng **BigDecimal.setScale(...)** với **RoundingMode** phù hợp.

Ví dụ làm tròn giá trị thập phân tới hai chữ số sau dấu phẩy:

~~~javascript
lab.numeric_examples.aggregate([
  { $limit: 1 },
  {
    $project: {
      _id: 0,
      rounded: {
        $round: [Decimal128("12.345"), 2]
      }
    }
  }
]);
~~~

Cần lưu ý **`$round`** của MongoDB dùng kiểu làm tròn **round half to even** đối với trường hợp đúng giữa hai giá trị có thể làm tròn. Quy tắc kế toán/thuế có thể khác; hãy quy định cụ thể trước khi triển khai.

## 6. Chuyển đổi giữa các kiểu số

MongoDB hỗ trợ các biểu thức:

| Toán tử aggregation | Kết quả dự định | Rủi ro cần kiểm soát |
| --- | --- | --- |
| `$toInt` | int32 | Lỗi nếu vượt miền; phần thập phân bị cắt khi chuyển từ kiểu số hỗ trợ |
| `$toLong` | int64 | Lỗi nếu vượt miền; phần thập phân bị cắt |
| `$toDouble` | double | Có thể mất độ chính xác khi đổi từ long hoặc decimal |
| `$toDecimal` | Decimal128 | Không tự phục hồi giá trị ban đầu của dữ liệu double đã làm tròn |
| `$convert` | Kiểu chỉ định | Có thể cấu hình `onError` và `onNull` khi dữ liệu đầu vào bẩn |

Ví dụ đổi chuỗi thập phân sang Decimal128, chấp nhận dữ liệu sai mà không làm dừng cả pipeline:

~~~javascript
lab.raw_prices.drop();
lab.raw_prices.insertMany([
  { _id: 1, raw: "12.50" },
  { _id: 2, raw: "7.30" },
  { _id: 3, raw: "invalid" },
  { _id: 4, raw: null }
]);

lab.raw_prices.aggregate([
  {
    $project: {
      _id: 1,
      raw: 1,
      value: {
        $convert: {
          input: "$raw",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

Kết quả hai tài liệu đầu có giá trị **Decimal128("12.50")** và **Decimal128("7.30")**; hai tài liệu còn lại có **value: null**. Trong bài toán thật, nên tách bản ghi lỗi để sửa nguồn dữ liệu, thay vì mặc định coi mọi giá trị không đổi được là số không.

Nếu đã biết đầu vào sạch, có thể rút gọn:

~~~javascript
lab.raw_prices.aggregate([
  { $match: { _id: 1 } },
  {
    $project: {
      original: "$raw",
      decimalValue: { $toDecimal: "$raw" }
    }
  }
]);
~~~

**Chuyển `Double(0.1)` sang Decimal128 không giống như đọc thẳng chuỗi `"0.1"` để tạo Decimal128.** Double lưu giá trị gần đúng; việc chuyển kiểu sau khi lưu thường không thể hoàn nguyên chính xác giá trị thập phân mà người dùng đã nhập. Nên chuyển trực tiếp từ biểu diễn văn bản/BigDecimal chính xác ngay từ điểm nhận dữ liệu nếu bài toán yêu cầu tính đúng theo thập phân.

## 7. Extended JSON: giữ lại kiểu khi trao đổi dữ liệu

JSON thông thường không có cách cú pháp riêng để phân biệt int32, int64, double và Decimal128. MongoDB có **Extended JSON (EJSON) v2** để mô tả kiểu BSON trong chuỗi JSON. Ở chế độ **Canonical**, bốn kiểu số có dạng:

~~~json
{
  "i32": { "$numberInt": "42" },
  "i64": { "$numberLong": "9007199254740993" },
  "dbl": { "$numberDouble": "0.1" },
  "dec": { "$numberDecimal": "0.10" }
}
~~~

Phân biệt hai chế độ:

- **Canonical EJSON:** ưu tiên giữ thông tin kiểu; hữu ích cho kiểm thử dữ liệu, trao đổi dữ liệu mong muốn round-trip và xuất/nhập cần xác định chính xác BSON type.
- **Relaxed EJSON:** ưu tiên dễ đọc; một số int32, int64 hoặc double hữu hạn có thể hiển thị như số JSON thông thường, vì vậy không đảm bảo giữ được loại số khi đi qua một JSON parser bất kỳ.

Ví dụ EJSON đối với tài liệu đã lấy từ MongoDB:

~~~javascript
const sample = lab.numeric_examples.findOne({ _id: "int64" });

// Canonical EJSON giữ nhãn kiểu Long:
EJSON.stringify(sample, null, 2, { relaxed: false });
~~~

Khi chuyển qua REST API sử dụng JSON thuần, một hệ thống JavaScript có thể parse giá trị nguyên lớn thành Number và làm mất chữ số. Các giao diện có yêu cầu giữ chính xác long thường truyền dạng **chuỗi** hoặc **EJSON** rồi khôi phục sang Long/BigInt theo hợp đồng API. Không giả định mọi REST client tự hiểu các khóa EJSON nếu chưa có bước giải mã tương ứng.

## 8. Ánh xạ BSON numeric types trong Java

Với **MongoDB Java Driver**, có thể biểu diễn bốn kiểu bằng các kiểu Java tương ứng:

| Java | BSON thường được ghi | Ghi chú |
| --- | --- | --- |
| `int` / `Integer` | int32 | Có dấu, 32 bit |
| `long` / `Long` | int64 | Có dấu, 64 bit, nguyên chính xác |
| `double` / `Double` | double | IEEE 754 binary64 |
| `org.bson.types.Decimal128` | Decimal128 | Dùng với `BigDecimal` để tạo giá trị |
| `java.math.BigDecimal` | Phụ thuộc cấu hình codec/mapping | Cần kiểm tra framework; không mặc định mọi mapper đều ghi Decimal128 |

Ví dụ sử dụng Java Driver với kiểu tường minh:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;
import java.math.BigDecimal;

public class NumericTypesExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create("mongodb://localhost:27017")) {
            MongoCollection<Document> collection = client
                    .getDatabase("bson_numeric_lab")
                    .getCollection("java_numeric_types");

            Document document = new Document("_id", "java-example")
                    .append("quantity", 42)                      // BSON int32
                    .append("totalBytes", 9007199254740993L)    // BSON int64
                    .append("measurement", 0.1d)                 // BSON double
                    .append("amount",
                            new Decimal128(new BigDecimal("19.90"))); // Decimal128

            collection.replaceOne(
                    new Document("_id", "java-example"),
                    document,
                    new com.mongodb.client.model.ReplaceOptions().upsert(true)
            );

            System.out.println(collection.find(
                    new Document("_id", "java-example")).first());
        }
    }
}
~~~

Giải thích:

- Hậu tố **L** ở literal Java yêu cầu kiểu long; Java giữ chính xác giá trị **9007199254740993L**.
- **0.1d** là số thực nhị phân gần đúng.
- **new BigDecimal("19.90")** tạo giá trị thập phân từ chuỗi. Tránh **new BigDecimal(0.1)** nếu mục đích là đúng giá trị thập phân **0.1**, bởi constructor này ghi nhận giá trị double nhị phân gần đúng.
- **Decimal128** có giới hạn 34 chữ số; Java **BigDecimal** có thể có độ chính xác lớn hơn. Phải kiểm soát việc chuyển từ BigDecimal sang Decimal128 khi số vượt giới hạn đích.

Trong **Spring Data MongoDB**, một trường Java **BigDecimal** có thể cần khai báo kiểu lưu BSON để không dùng cách chuyển đổi mặc định của framework. Ví dụ:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class ProductPrice {
    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Cách ánh xạ thực tế còn phụ thuộc phiên bản Spring Data và codec/converter cấu hình cho dự án. Khi dữ liệu tiền cần hợp đồng ổn định, nên kiểm tra kiểu BSON thực lưu bằng **`$type`**.

## 9. Chọn kiểu theo bài toán

### 9.1. Số lượng và bộ đếm

**int32** hợp lý khi đã biết giới hạn nghiệp vụ thấp hơn 2³¹, chẳng hạn số item của một dòng đơn hàng. **int64** hợp lý với lượt truy cập lớn, tổng số message đã xử lý hoặc kích thước file tính bằng byte. Nếu số đếm có khả năng vượt miền long trong tương lai rất xa, thiết kế cần cách lưu trữ chuyên biệt.

Khi thực thi toán tử cập nhật **`$inc`**, kiểu lưu và khả năng vượt miền cần được quan sát; không nên mặc định mọi giá trị sẽ luôn ở kiểu số ban đầu sau nhiều lần tăng.

### 9.2. Đơn giá và số tiền

Có hai cách phổ biến:

1. **Decimal128:** lưu số tiền dưới đơn vị chính (ví dụ `Decimal128("125.50")`), tính toán theo thập phân; phù hợp giá có nhiều chữ số sau dấu phẩy và yêu cầu rõ về rounding.
2. **int64 ở đơn vị nhỏ nhất:** lưu **12.550 xu** thay cho **125,50 đơn vị tiền**, nếu một đơn vị chính tương đương 100 xu. Phép cộng/trừ số nguyên chính xác nhưng ứng dụng cần quản lý hệ số quy đổi, giới hạn overflow và đồng tiền.

Không phải đồng tiền nào cũng có hai chữ số thập phân. Thiết kế tài chính nên lưu **mã tiền tệ** cùng giá trị và xác định đơn vị quy đổi một cách nhất quán.

**Double thường không phù hợp làm giá trị tiền cần đối soát chính xác**. Kể cả khi UI luôn làm tròn hai chữ số, sai số có thể xuất hiện trước bước hiển thị.

### 9.3. Đo lường, tỷ lệ và khoa học dữ liệu

Double thường là lựa chọn tự nhiên cho nhiệt độ, tọa độ, cảm biến, điểm số mô hình, tỷ lệ phần trăm và số liệu thống kê. Khi so sánh số thực, dùng dung sai phù hợp thay vì luôn yêu cầu bằng tuyệt đối.

Ví dụ, nếu business rule yêu cầu “nhiệt độ trong khoảng 20–30 độ” thì truy vấn khoảng thường có ý nghĩa hơn so sánh một kết quả double với duy nhất một giá trị phân số:

~~~javascript
lab.sensor_readings.find({
  temperature: { $gte: 20.0, $lte: 30.0 }
});
~~~

Collection **sensor_readings** ở đây là ví dụ đặt tên cho ứng dụng đo lường; không phải dữ liệu đã được tạo ở phần thực hành trước.

### 9.4. Khi nên chuẩn hóa loại số?

Nếu một trường **amount** có tài liệu là int32, có tài liệu là double, có tài liệu là Decimal128, ứng dụng sẽ khó bảo đảm phép tính thống nhất. Cần chọn một **kiểu chuẩn ở biên ghi**, dùng migration có kiểm soát cho dữ liệu cũ và áp dụng MongoDB schema validation khi phù hợp.

Ví dụ validator yêu cầu trường **amount** là Decimal128 (chưa áp dụng lên các collection ví dụ khác):

~~~javascript
lab.createCollection("decimal_only", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["amount"],
      properties: {
        amount: {
          bsonType: "decimal",
          description: "amount phai duoc ghi duoi dang Decimal128"
        }
      }
    }
  }
});

lab.decimal_only.insertOne({
  amount: Decimal128("15.75")
});

// Bị validator từ chối do kiểu được lưu là int32:
lab.decimal_only.insertOne({
  amount: Int32(15)
});
~~~

Trong ứng dụng thực, cân nhắc cấu hình **validationAction**, **validationLevel**, dữ liệu legacy và chính sách cập nhật schema trước khi triển khai validator. Nếu collection **decimal_only** đã tồn tại, phải dùng cơ chế thay đổi validator thay vì chạy lại **createCollection**.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “Số JSON nào cũng giống nhau” | Mất thông tin kiểu khi serialize/deserialize | Dùng constructor BSON hoặc Canonical EJSON khi cần round-trip |
| “Số nguyên vượt int32 sẽ tự thành long” | mongosh có thể ghi thành double, gây mất chính xác | Ghi tường minh bằng `Long("...")` |
| “Dùng double vẫn chính xác nếu in ra 2 chữ số” | Sai số tích lũy trước khi hiển thị | Dùng Decimal128 hoặc số nguyên đơn vị nhỏ nhất cho tiền |
| “Chuyển double sang Decimal128 là khôi phục dữ liệu” | Giá trị đầu vào đã bị làm tròn từ trước | Nhận dữ liệu từ chuỗi/BigDecimal có ý nghĩa chính xác |
| “BigDecimal trong Java chắc chắn thành Decimal128” | Lưu thành kiểu BSON khác nếu mapper cấu hình khác | Khai báo target type/codec rõ ràng, kiểm tra bằng `$type` |
| “Hai số bằng nhau thì cùng BSON type” | Truy vấn số 1 có thể khớp int32, int64, double, decimal | Dùng `$type` để phân biệt kiểu |
| “Decimal128 có độ chính xác vô hạn” | Vẫn có rounding/overflow khi quá 34 chữ số | Chọn scale, rounding và kiểm soát giới hạn |
| “Mọi số long đều đưa qua JavaScript Number được” | Mất chữ số khi vượt vùng safe integer | Dùng chuỗi, đối tượng Long hoặc API hỗ trợ BigInt an toàn |

## 11. Bài thực hành tự kiểm tra

Sử dụng collection **numeric_examples** đã tạo ở mục 3, thực hiện các yêu cầu sau:

1. Viết aggregation hiển thị `_id`, `value` và `$type` của từng tài liệu. Phân biệt rõ **long** và **double** dù cùng chiếm 8 byte giá trị.
2. Thêm một tài liệu với `Long("9223372036854775807")`. Đọc lại mà không ép sang JavaScript Number và giải thích vì sao đây là giới hạn trên int64.
3. Tính `0.1 + 0.2` bằng double và bằng Decimal128 với `$add`. Quan sát kết quả và giải thích vai trò của cơ số biểu diễn.
4. Tạo hai tài liệu có **Decimal128("19.90")** và **Decimal128("10.10")**, dùng `$sum` tính tổng; xác định kiểu của kết quả bằng `$type`.
5. Thử chuyển chuỗi `"42"` sang int32, long, double và decimal bằng bốn toán tử chuyển đổi. Sau đó thử chuỗi không hợp lệ để thấy sự khác biệt giữa `$toDecimal` và `$convert` có `onError`.
6. Tạo tài liệu có giá trị `Int32(1)`, `Long("1")`, `Double(1)` và `Decimal128("1")`; so sánh kết quả truy vấn bằng giá trị với truy vấn theo BSON type.

Các câu hỏi cần tự trả lời: **Kiểu nào lưu chính xác số nguyên lớn? Kiểu nào phù hợp số tiền? Khi nào cần Decimal128? Vì sao một phép chuyển kiểu sau khi dữ liệu đã bị làm tròn không thể khôi phục chính xác giá trị ban đầu?**

## 12. Ghi nhớ khi thiết kế schema MongoDB

Lựa chọn kiểu số là một phần của **hợp đồng dữ liệu**, không chỉ là chi tiết tối ưu dung lượng. Hãy xác định khoảng giá trị, đơn vị, yêu cầu chính xác, hành vi cộng/trừ/tổng hợp, kiểu dữ liệu ở Java/JavaScript và định dạng truyền qua API ngay từ khi thiết kế trường.

- Dùng **int32** cho số nguyên nhỏ có miền giá trị được kiểm soát.
- Dùng **int64** cho số nguyên lớn cần bảo toàn từng đơn vị.
- Dùng **double** cho số thực đo lường chấp nhận sai số nhị phân.
- Dùng **Decimal128** cho số thập phân cần độ chính xác và quy tắc làm tròn rõ ràng.

### Tài liệu tham khảo chính thức

- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — mã kiểu, bí danh kiểu số và quy tắc BSON.
- [mongosh Data Types](https://www.mongodb.com/docs/mongodb-shell/reference/data-types/) — cách tạo Int32, Long, Double, Decimal128 và hành vi numeric mặc định của mongosh.
- [Extended JSON (v2)](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — kiểu số ở Canonical và Relaxed JSON.
- [`$sum` (accumulator)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/) — nâng kiểu và xử lý overflow.
- [`$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/) — chuyển đổi và xử lý giá trị lỗi/null.
