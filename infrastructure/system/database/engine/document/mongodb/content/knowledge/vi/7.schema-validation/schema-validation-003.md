# Trường bắt buộc, enum, khoảng giá trị và quy tắc chuỗi trong MongoDB Schema Validation

MongoDB là cơ sở dữ liệu tài liệu có **schema linh hoạt**: các document trong cùng collection có thể không giống hệt nhau về trường và kiểu dữ liệu. Tính linh hoạt đó giúp phát triển nhanh, nhưng cũng tạo nguy cơ dữ liệu sai quy ước, ví dụ một sản phẩm thiếu `sku`, trạng thái `"publised"` bị gõ nhầm, số lượng tồn kho âm hoặc mã hàng không đúng định dạng.

**Schema validation** cho phép đặt điều kiện kiểm tra **ở phía MongoDB** khi ứng dụng ghi tài liệu. Bài này tập trung vào bốn nhóm quy tắc phổ biến:

1. **Trường bắt buộc:** field nào phải xuất hiện trong document?
2. **Enum:** field chỉ được nhận những giá trị nào?
3. **Khoảng giá trị:** con số phải nằm trong giới hạn nào?
4. **Quy tắc chuỗi:** chuỗi phải có độ dài và định dạng ra sao?

Sau khi thực hành, bạn sẽ tự tạo validator bằng `$jsonSchema`, đọc lỗi khi dữ liệu không hợp lệ, phân biệt thiếu trường với giá trị `null`, thay đổi quy tắc bằng `collMod` và hiểu cách áp dụng schema cho dữ liệu đang tồn tại.

## 1. Schema validation nằm ở đâu trong luồng ghi dữ liệu?

Xét collection `products` do nhiều nguồn ghi: trang quản trị, REST API, batch import và tác vụ tự động. Mỗi client có thể kiểm tra input trước khi ghi, nhưng việc chỉ dựa vào validation của ứng dụng không đảm bảo mọi đường ghi đều thống nhất.

~~~text
Ứng dụng web ──────┐
REST API ──────────┤
Script import ─────┼──> MongoDB: products
Batch job ─────────┘          |
                              v
                       Collection validator
                         |             |
                    Hợp lệ          Không hợp lệ
                         |             |
                     Chấp nhận     Từ chối ghi
                                   (nếu action=error)
~~~

MongoDB cung cấp **`validator` ở cấp collection**, thường dùng toán tử `$jsonSchema` để mô tả hình dạng document, kiểu BSON và ràng buộc nội dung. Khi `validationAction` là `"error"`, thao tác ghi tạo ra tài liệu không đáp ứng validator sẽ bị từ chối.

Ví dụ schema nghiệp vụ:

| Trường | Quy tắc dự kiến | Ví dụ hợp lệ |
| --- | --- | --- |
| `sku` | Bắt buộc, chuỗi 4–12 ký tự, chữ cái in hoa mở đầu, sau đó chỉ gồm A–Z, 0–9, `_` hoặc `-` | `"MOUSE-01"` |
| `title` | Bắt buộc, chuỗi dài 3–120 ký tự | `"Chuột không dây"` |
| `status` | Bắt buộc, chỉ thuộc `draft`, `published`, `archived` | `"draft"` |
| `stock` | Bắt buộc, BSON int32, trong khoảng 0–100000 | `Int32(30)` |
| `price` | Bắt buộc, BSON Decimal128, không âm | `Decimal128("259000.00")` |
| `note` | Không bắt buộc; nếu có phải là chuỗi tối đa 250 ký tự | `"Giao nội thành"` |

Đây là **quy tắc dữ liệu**, không phải một bản sao của Java entity hay JSON Schema dùng ở frontend. Hợp đồng ở MongoDB cần tính tới **BSON type**, đặc biệt với số.

## 2. Chuẩn bị môi trường và collection

Các lệnh sau chạy trong **mongosh** nối tới MongoDB đã hoạt động. Dùng database riêng cho bài học.

~~~javascript
const labDb = db.getSiblingDB("schema_validation_lab");

// Chỉ xóa collection thực hành trong database này.
// Nếu đã có dữ liệu cần giữ, bỏ bước drop() và dùng tên khác.
labDb.products.drop();
~~~

Lệnh `db.createCollection()` có thể khai báo `validator` ngay lúc tạo. Ta bắt đầu bằng schema đầy đủ cho `products`:

~~~javascript
labDb.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "title", "status", "stock", "price"],
      properties: {
        sku: {
          bsonType: "string",
          minLength: 4,
          maxLength: 12,
          pattern: "^[A-Z][A-Z0-9_-]{3,11}$",
          description: "SKU phải có 4-12 ký tự, bắt đầu bằng A-Z"
        },
        title: {
          bsonType: "string",
          minLength: 3,
          maxLength: 120,
          description: "Tên sản phẩm dài từ 3 đến 120 ký tự"
        },
        status: {
          bsonType: "string",
          enum: ["draft", "published", "archived"],
          description: "Trạng thái phải nằm trong danh sách cho phép"
        },
        stock: {
          bsonType: "int",
          minimum: 0,
          maximum: 100000,
          description: "Tồn kho là int32 từ 0 đến 100000"
        },
        price: {
          bsonType: "decimal",
          minimum: 0,
          description: "Đơn giá phải là Decimal128 không âm"
        },
        note: {
          bsonType: "string",
          maxLength: 250
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

**Cấu trúc cần nhớ:**

- `bsonType: "object"`: toàn bộ document phải là object BSON.
- `required`: danh sách **tên field phải tồn tại**.
- `properties`: các ràng buộc áp dụng **khi field tương ứng xuất hiện**.
- `bsonType` trong từng property: kiểm tra loại BSON, ví dụ `"string"`, `"int"`, `"decimal"`.
- `enum`: liệt kê giá trị được chấp nhận.
- `minimum`/`maximum`: ràng buộc cận số.
- `minLength`/`maxLength`/`pattern`: ràng buộc chuỗi.
- `validationLevel` và `validationAction`: điều khiển phạm vi kiểm tra và phản ứng khi có lỗi.

Mặc định MongoDB vẫn cho phép các trường **không được khai báo** trong `properties`, vì ta chưa đặt `additionalProperties: false`. Phần về quy tắc trường bổ sung sẽ giải thích khi nào nên thắt chặt điều này.

### 2.1. Thêm một document hợp lệ

~~~javascript
labDb.products.insertOne({
  _id: "P-001",
  sku: "MOUSE-01",
  title: "Chuột không dây",
  status: "draft",
  stock: Int32(30),
  price: Decimal128("259000.00"),
  note: "Giao nội thành"
});

labDb.products.findOne({ _id: "P-001" });
~~~

Thao tác được chấp nhận vì document có đủ năm trường bắt buộc và mọi giá trị đều thỏa điều kiện.

**Đối với kiểu số:** `stock` được tạo rõ ràng bằng `Int32(...)`, `price` bằng `Decimal128(...)`. Việc truyền JavaScript Number thông thường có thể cho BSON type khác với dự kiến; schema sẽ bắt sai khác này khi `bsonType` được đặt chặt.

## 3. Trường bắt buộc với `required`

### 3.1. Có mặt khác với có giá trị hợp lệ

`required` là một **mảng tên field** ở cấp object đang kiểm tra:

~~~javascript
{
  bsonType: "object",
  required: ["sku", "status"],
  properties: {
    sku: { bsonType: "string" },
    status: { bsonType: "string" }
  }
}
~~~

Điều này có nghĩa:

- Thiếu hẳn `sku` → không hợp lệ.
- Có `sku: null` → **đã thỏa việc “có field”**, nhưng vẫn **không hợp lệ** với `bsonType: "string"`.
- Có `sku: ""` → thỏa `required` và `bsonType: "string"`, nhưng nếu nghiệp vụ cấm chuỗi rỗng phải thêm `minLength` hoặc `pattern`.

Trong validator của `products`, thử ghi một document thiếu trường `sku`:

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-MISSING",
    title: "Bàn phím cơ",
    status: "draft",
    stock: Int32(5),
    price: Decimal128("900000.00")
  });
} catch (error) {
  print("Bị từ chối: " + error.message);
}
~~~

MongoDB từ chối thao tác vì `sku` nằm trong danh sách `required`. Khi `validationAction: "error"`, lỗi thường có mã **121 (DocumentValidationFailure)** và thông tin chi tiết về quy tắc thất bại, tùy phiên bản máy chủ và driver.

### 3.2. Trường tùy chọn nhưng vẫn phải đúng kiểu

`note` không có trong `required`, nên document **không có `note`** được phép. Tuy nhiên, nếu có `note` thì vẫn phải là chuỗi và dài không quá 250 ký tự.

~~~javascript
// Hợp lệ: không có note.
labDb.products.insertOne({
  _id: "P-002",
  sku: "KEY-200",
  title: "Bàn phím cơ",
  status: "draft",
  stock: Int32(7),
  price: Decimal128("900000.00")
});

// Không hợp lệ: note có mặt nhưng giá trị null
// không thuộc bsonType "string".
try {
  labDb.products.updateOne(
    { _id: "P-002" },
    { $set: { note: null } }
  );
} catch (error) {
  print("Lỗi note: " + error.message);
}
~~~

Nếu nghiệp vụ cho phép cả chuỗi hoặc `null`, thay quy tắc thành:

~~~javascript
note: {
  bsonType: ["string", "null"],
  maxLength: 250
}
~~~

`required` không tự tạo giá trị mặc định. Nếu muốn giá trị mặc định cho một field, hãy thiết kế ở ứng dụng hoặc quy trình ghi; đừng kỳ vọng MongoDB tự chèn `status: "draft"` chỉ vì đã khai báo enum.

### 3.3. `required` với object lồng nhau

Mỗi object cần có **`required` riêng tại đúng cấp** của nó. Ví dụ một trường `shipping` là tùy chọn; nhưng nếu có `shipping` thì bắt buộc có `city` và `postalCode`:

~~~javascript
{
  bsonType: "object",
  properties: {
    shipping: {
      bsonType: "object",
      required: ["city", "postalCode"],
      properties: {
        city: {
          bsonType: "string",
          minLength: 2
        },
        postalCode: {
          bsonType: "string",
          pattern: "^[0-9]{5,6}$"
        }
      }
    }
  }
}
~~~

Vì `shipping` không nằm trong `required` của object **ngoài cùng**, thiếu hoàn toàn trường này vẫn hợp lệ. Nhưng nếu một document chứa `shipping: { city: "Hanoi" }` thì không hợp lệ do thiếu `postalCode`.

Nếu muốn `shipping` luôn xuất hiện, bổ sung `"shipping"` vào mảng `required` của object ngoài cùng.

## 4. Danh sách giá trị cho phép bằng `enum`

`enum` định nghĩa một **tập hữu hạn các giá trị** mà field có thể nhận. Trường `status` của sản phẩm:

~~~javascript
status: {
  bsonType: "string",
  enum: ["draft", "published", "archived"]
}
~~~

Ba giá trị này có ý nghĩa:

| Giá trị | Mô tả trong ví dụ |
| --- | --- |
| `draft` | Sản phẩm đang soạn |
| `published` | Sản phẩm được công bố |
| `archived` | Sản phẩm đã lưu trữ/ẩn khỏi luồng hoạt động |

Khi ứng dụng vô tình ghi `"publised"`, MongoDB sẽ bắt lỗi thay vì tạo một trạng thái mới không thuộc hợp đồng dữ liệu.

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-ENUM",
    sku: "MOUSE-02",
    title: "Chuột có dây",
    status: "publised",       // Sai chính tả
    stock: Int32(10),
    price: Decimal128("99000.00")
  });
} catch (error) {
  print("Lỗi enum: " + error.message);
}
~~~

**Các lưu ý khi dùng enum:**

- Giá trị phải đúng với danh sách khai báo; `"PUBLISHED"` và `"published"` không được coi là đồng nhất trong danh sách như trên.
- Enum không cung cấp cơ chế chuyển trạng thái hợp lệ, ví dụ `draft → published → archived`. Nó chỉ kiểm tra **giá trị cuối cùng** được ghi có nằm trong tập cho phép hay không.
- Khi thêm một giá trị mới vào enum, cần cập nhật contract của API, client, dữ liệu và validator theo kế hoạch triển khai.
- Nếu field không bắt buộc, thiếu field vẫn hợp lệ, trừ khi có quy tắc khác yêu cầu nó.
- Nếu `null` được chấp nhận về nghiệp vụ, cần thiết kế cả `enum` và `bsonType` phù hợp; ví dụ `enum: ["draft", null]` kết hợp `bsonType: ["string", "null"]`.

Không nên dùng một enum cực lớn chứa hàng nghìn mã sản phẩm hay mã đối tác luôn thay đổi; lúc đó dữ liệu tham chiếu, collection riêng hoặc logic kiểm tra ở ứng dụng có thể phù hợp hơn.

## 5. Giới hạn số bằng `minimum` và `maximum`

Với các trường số, MongoDB có thể dùng cận dưới và cận trên để từ chối giá trị nằm ngoài khoảng cho phép:

~~~javascript
stock: {
  bsonType: "int",
  minimum: 0,
  maximum: 100000
}
~~~

Ở ví dụ này, cả **0** và **100000** đều hợp lệ. Các cận `minimum` và `maximum` là **bao gồm biên**. Giá trị `-1` và `100001` bị từ chối.

| Giá trị BSON của `stock` | Hợp lệ? | Lý do |
| --- | --- | --- |
| `Int32(0)` | Có | Bằng cận dưới |
| `Int32(500)` | Có | Trong khoảng |
| `Int32(100000)` | Có | Bằng cận trên |
| `Int32(-1)` | Không | Nhỏ hơn 0 |
| `Int32(100001)` | Không | Lớn hơn 100000 |
| `Long("50")` | Không | Giá trị 50 nằm trong khoảng nhưng BSON type là long |
| `"50"` | Không | Chuỗi, không phải int32 |

Thử cập nhật vượt miền nghiệp vụ:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $set: { stock: Int32(-1) } }
  );
} catch (error) {
  print("Lỗi khoảng giá trị: " + error.message);
}
~~~

Do validation xét **document sau cập nhật**, thao tác trên bị từ chối và `stock` trong `P-001` giữ nguyên giá trị đã lưu.

### 5.1. Kiểu BSON và khoảng giá trị là hai ràng buộc khác nhau

Giả sử `price` là đơn giá bắt buộc lưu bằng Decimal128:

~~~javascript
price: {
  bsonType: "decimal",
  minimum: 0
}
~~~

Lệnh dưới đây bị từ chối, dù 50000 là một số không âm, vì kiểu BSON không đúng:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $set: { price: 50000 } } // không phải Decimal128 tường minh
  );
} catch (error) {
  print("Lỗi kiểu giá: " + error.message);
}
~~~

Cách ghi rõ ràng:

~~~javascript
labDb.products.updateOne(
  { _id: "P-001" },
  { $set: { price: Decimal128("50000.00") } }
);
~~~

Khi cần cho phép nhiều kiểu số BSON ở một trường, có thể khai báo `bsonType` là mảng, ví dụ `["int", "long"]`. Tuy vậy, trộn kiểu số có thể gây rắc rối cho phép tính và ánh xạ ứng dụng; nên chuẩn hóa khi có thể.

### 5.2. Giá trị nguyên, giá trị thập phân và làm tròn

Validator có thể kiểm tra khoảng giá trị và BSON type nhưng **không tự định nghĩa chính sách làm tròn** hoặc đơn vị tiền tệ. Ví dụ `Decimal128("10.1234")` vẫn đáp ứng `minimum: 0`.

Nếu đơn giá chỉ được có hai chữ số thập phân, cần bổ sung giải pháp phù hợp ở tầng nhận dữ liệu hoặc một quy tắc kiểm tra được thiết kế riêng. Không nên nhầm `maximum` với quy tắc precision/scale.

Một ràng buộc như `maximum: 100000` cũng **không đảm bảo uniqueness**, tức hai document có cùng giá hoặc stock vẫn có thể được lưu. Tính duy nhất của field được đảm bảo bằng **unique index** hoặc quy tắc xử lý khác.

## 6. Độ dài chuỗi bằng `minLength` và `maxLength`

Hai keyword này ràng buộc độ dài của giá trị chuỗi:

~~~javascript
title: {
  bsonType: "string",
  minLength: 3,
  maxLength: 120
}
~~~

| `title` | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `"Bút"` | Có | Chuỗi có độ dài từ 3 đến 120 ký tự |
| `"A"` | Không | Quá ngắn |
| `""` | Không | Chuỗi rỗng |
| `"   "` | Có theo riêng hai quy tắc độ dài | Có đủ ba ký tự nhưng không mang nội dung |
| Chuỗi dài hơn 120 ký tự | Không | Vượt maxLength |
| `null` | Không | Không thuộc kiểu string đã yêu cầu |

Các giới hạn độ dài không thay thế việc **loại khoảng trắng không mong muốn**, chuẩn hóa Unicode hoặc kiểm tra nội dung có nghĩa.

Nếu bắt buộc tên không được toàn khoảng trắng, có thể thêm `pattern` để yêu cầu ít nhất một ký tự không phải whitespace:

~~~javascript
title: {
  bsonType: "string",
  minLength: 3,
  maxLength: 120,
  pattern: "\\S"
}
~~~

Trong JavaScript string, `"\\S"` tạo ra biểu thức chính quy `\S`. Một pattern không có neo như `\S` có thể khớp **bất kỳ vị trí nào** chứa ký tự khác khoảng trắng; nó không tự cấm khoảng trắng ở hai đầu. Nếu yêu cầu cấm khoảng trắng đầu/cuối, cần một biểu thức có neo phù hợp hoặc chuẩn hóa và kiểm tra ở ứng dụng.

### 6.1. Có cần coi số ký tự là số byte?

`minLength` và `maxLength` là ràng buộc **độ dài chuỗi**, không phải cách giới hạn byte của toàn document BSON. Tiếng Việt và emoji có thể chiếm nhiều byte UTF-8 hơn ký tự Latin thông thường. Nếu hệ thống có giới hạn byte theo giao thức hoặc hệ thống ngoài, hãy kiểm tra riêng giới hạn byte đó.

Với tên hiển thị trong ngôn ngữ tự nhiên, không nên tùy tiện dùng regex chỉ cho phép `[A-Za-z]`: biểu thức này sẽ loại bỏ nhiều chữ cái có dấu, khoảng trắng hợp lệ và ký tự từ các hệ chữ khác.

## 7. Định dạng chuỗi bằng `pattern`

Keyword `pattern` nhận **chuỗi biểu thức chính quy (regular expression)**. MongoDB áp dụng regex để kiểm tra giá trị chuỗi; nếu không khớp thì document bị từ chối.

Trong validator đầu bài, `sku` có:

~~~javascript
sku: {
  bsonType: "string",
  minLength: 4,
  maxLength: 12,
  pattern: "^[A-Z][A-Z0-9_-]{3,11}$"
}
~~~

Ý nghĩa từng phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `^` | Bắt đầu chuỗi |
| `[A-Z]` | Ký tự đầu tiên phải là chữ cái in hoa A–Z |
| `[A-Z0-9_-]` | Các ký tự tiếp theo có thể là A–Z, 0–9, `_` hoặc `-` |
| `{3,11}` | Lặp từ 3 đến 11 lần ở phần sau |
| `$` | Kết thúc chuỗi |

Biểu thức trên cho phép **tổng độ dài từ 4 đến 12 ký tự**; hai ràng buộc độ dài trong schema giúp mục đích nghiệp vụ rõ ràng hơn dù regex đã có điều kiện về chiều dài.

| SKU | Hợp lệ? | Lý do |
| --- | --- | --- |
| `MOUSE-01` | Có | Ký tự hợp lệ, dài 8 |
| `A123` | Có | Một ký tự đầu A và ba ký tự tiếp |
| `a123` | Không | Chữ đầu viết thường |
| `12AB` | Không | Không bắt đầu bằng chữ in hoa |
| `AB` | Không | Dưới 4 ký tự |
| `A12#5` | Không | Chứa ký tự `#` |
| `A123456789012` | Không | Dài hơn 12 ký tự |

### 7.1. Vì sao cần neo `^` và `$`?

Nếu chỉ viết:

~~~javascript
pattern: "[A-Z]{2}[0-9]{3}"
~~~

thì chuỗi `"xxxAB123yyy"` vẫn có thể khớp **một đoạn con**. Để yêu cầu **toàn bộ chuỗi** đúng định dạng, dùng:

~~~javascript
pattern: "^[A-Z]{2}[0-9]{3}$"
~~~

Tùy mục đích, không phải regex nào cũng cần neo; ví dụ kiểm tra tiêu đề có ít nhất một ký tự không phải khoảng trắng có thể dùng `\S` mà không cần neo.

### 7.2. Escape regex trong JavaScript và JSON

Khi schema được viết dưới dạng **JavaScript string** trong mongosh, dấu backslash của regex cần được escape thêm một lần. Ví dụ muốn khớp đúng sáu chữ số:

~~~javascript
pattern: "^[0-9]{6}$"

// Tương đương ý tưởng regex sử dụng \d:
pattern: "^\\d{6}$"
~~~

Với schema ở định dạng **JSON**, cú pháp escape chuỗi cũng yêu cầu `\\` để biểu diễn một dấu `\` của regex. Cần phân biệt giữa **regex thực tế** và **chuỗi chứa regex**.

### 7.3. Một số mẫu thông dụng

| Nhu cầu | `pattern` minh họa | Lưu ý |
| --- | --- | --- |
| Mã có hai chữ cái rồi ba số | `"^[A-Z]{2}[0-9]{3}$"` | Phân biệt hoa/thường |
| Mã bưu chính 5–6 chữ số ASCII | `"^[0-9]{5,6}$"` | Không áp dụng được cho mọi quốc gia |
| Ký tự chữ/số/`_`/`-` từ 4–20 | `"^[A-Za-z0-9_-]{4,20}$"` | Không cho dấu và khoảng trắng |
| Chuỗi chứa ít nhất một ký tự không trắng | `"\\S"` | Không loại bỏ khoảng trắng đầu/cuối |
| Chuỗi chỉ gồm chữ số ASCII | `"^[0-9]+$"` | Không thay thế kiểm tra giá trị số nguyên |

Regex đơn giản không đủ để xác minh các định dạng nhiều quy tắc như email có thể nhận thư, số điện thoại quốc tế hay mã định danh do bên thứ ba cấp. Những trường hợp đó cần parser/thư viện chuyên dụng và đôi khi phải xác minh thực tế.

## 8. Thử các document không hợp lệ

Để thấy mỗi nhóm quy tắc hoạt động, chạy các thao tác độc lập sau. Dùng `try/catch` để một lỗi không làm gián đoạn toàn bộ bài lab.

### 8.1. Thiếu trường bắt buộc

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-1",
    sku: "BOOK-01",
    title: "Sách MongoDB",
    // thiếu status
    stock: Int32(2),
    price: Decimal128("50000.00")
  });
} catch (e) {
  print("ERR-1: " + e.message);
}
~~~

### 8.2. Enum sai

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-2",
    sku: "BOOK-02",
    title: "Sách dữ liệu",
    status: "active",  // không thuộc danh sách enum
    stock: Int32(2),
    price: Decimal128("50000.00")
  });
} catch (e) {
  print("ERR-2: " + e.message);
}
~~~

### 8.3. Số ngoài khoảng

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-3",
    sku: "BOOK-03",
    title: "Sách về BSON",
    status: "draft",
    stock: Int32(100001),  // quá maximum
    price: Decimal128("50000.00")
  });
} catch (e) {
  print("ERR-3: " + e.message);
}
~~~

### 8.4. Chuỗi sai định dạng

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-4",
    sku: "book-04",     // chữ thường, không khớp pattern
    title: "Sách về index",
    status: "draft",
    stock: Int32(3),
    price: Decimal128("70000.00")
  });
} catch (e) {
  print("ERR-4: " + e.message);
}
~~~

### 8.5. Chuỗi quá ngắn

~~~javascript
try {
  labDb.products.insertOne({
    _id: "ERR-5",
    sku: "BOOK-05",
    title: "AB",        // ngắn hơn minLength: 3
    status: "draft",
    stock: Int32(3),
    price: Decimal128("70000.00")
  });
} catch (e) {
  print("ERR-5: " + e.message);
}
~~~

Sau các lệnh thất bại, collection vẫn chứa những document hợp lệ đã chèn thành công, ví dụ `P-001` và `P-002`:

~~~javascript
labDb.products.find(
  {},
  { _id: 1, sku: 1, status: 1, stock: 1, price: 1 }
);
~~~

**Lỗi kiểm tra schema không tự sửa input.** Ứng dụng nên hiển thị nguyên nhân dưới dạng có ý nghĩa với người dùng, sửa dữ liệu đầu vào hoặc dừng ghi và ghi nhận lỗi để xử lý.

## 9. Schema validation có áp dụng cho update không?

Có. Với cấu hình `validationLevel: "strict"` và `validationAction: "error"`, MongoDB kiểm tra **document sau thao tác update**. Điều này áp dụng cả khi lệnh chỉ sửa một field và vô tình khiến document không còn hợp lệ.

Ví dụ chuyển trạng thái sản phẩm sang giá trị cho phép:

~~~javascript
labDb.products.updateOne(
  { _id: "P-001" },
  { $set: { status: "published" } }
);
~~~

Cập nhật hợp lệ. Nhưng nếu xóa trường bắt buộc:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $unset: { sku: "" } }
  );
} catch (e) {
  print("Không thể bỏ trường sku: " + e.message);
}
~~~

Lệnh `$unset` khiến tài liệu thiếu `sku`, nên bị từ chối. Tài liệu nguồn vẫn giữ giá trị `sku` cũ.

Tương tự:

~~~javascript
try {
  labDb.products.updateOne(
    { _id: "P-001" },
    { $inc: { stock: -1000 } }
  );
} catch (e) {
  print("Không thể làm stock âm: " + e.message);
}
~~~

Nếu kết quả cuối cùng của `$inc` vi phạm `minimum: 0`, thao tác không được chấp nhận.

**Không nhầm với quy tắc chuyển trạng thái:** validator enum chấp nhận `draft`, `published` và `archived`, nhưng không ngăn tự động việc cập nhật `archived → draft`. Để kiểm soát transition, cần điều kiện update, logic nghiệp vụ hoặc quy tắc nâng cao.

## 10. `additionalProperties`: khóa hoặc mở field bổ sung

Validator ban đầu chỉ áp đặt quy tắc cho các field đã định nghĩa; một document có thêm `color: "black"` vẫn có thể được chấp nhận.

~~~javascript
labDb.products.updateOne(
  { _id: "P-001" },
  { $set: { color: "black" } }
);
~~~

Nếu muốn chỉ cho phép những field đã khai báo, dùng:

~~~javascript
{
  bsonType: "object",
  required: ["sku"],
  additionalProperties: false,
  properties: {
    _id: {},
    sku: { bsonType: "string" }
  }
}
~~~

Trong MongoDB, `_id` thường tồn tại trong document; **phải khai báo `_id` trong `properties` khi dùng `additionalProperties: false`** nếu không muốn document bị từ chối chỉ vì có `_id`.

Hạn chế cần cân nhắc: `additionalProperties: false` khiến việc mở rộng schema khó hơn, vì mỗi field mới đều phải được cập nhật validator trước khi ghi. Với nhiều ứng dụng phát triển liên tục, cách hữu ích là khóa các field nhạy cảm và kiểm soát phần còn lại bằng validation ở ứng dụng hoặc các quy tắc cấp field, thay vì cấm mọi field chưa biết ngay từ đầu.

## 11. Xem và thay đổi validator bằng `collMod`

### 11.1. Xem cấu hình hiện tại

~~~javascript
labDb.getCollectionInfos({ name: "products" });
~~~

Trong thông tin trả về, `options.validator` chứa schema, `options.validationLevel` và `options.validationAction` chứa chính sách áp dụng.

Có thể lấy object `$jsonSchema` đang sử dụng:

~~~javascript
const info = labDb.getCollectionInfos({ name: "products" })[0];
const currentSchema = info.options.validator.$jsonSchema;

printjson(currentSchema);
~~~

### 11.2. Thay đổi quy tắc khi nghiệp vụ phát triển

Giả sử muốn cho phép tiêu đề dài tối đa **150** ký tự thay vì **120**. Tạo định nghĩa mới từ cấu hình đã đọc rồi dùng lệnh `collMod`:

~~~javascript
// Dùng sau bước đọc currentSchema ở trên.
const newSchema = EJSON.parse(EJSON.stringify(currentSchema));

newSchema.properties.title.maxLength = 150;

labDb.runCommand({
  collMod: "products",
  validator: { $jsonSchema: newSchema },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Lệnh cập nhật **quy tắc của collection**, không tự viết lại tài liệu đã tồn tại. Khi thay đổi schema, ứng dụng và schema database cần cùng hiểu giá trị mới.

Nếu thêm trạng thái enum mới, làm tương tự:

~~~javascript
// Ví dụ thay cho việc sửa title ở trên, hoặc sau khi đã cập nhật:
newSchema.properties.status.enum = [
  "draft", "published", "archived", "discontinued"
];

// Chỉ có hiệu lực sau khi chạy collMod với validator mới.
~~~

Trong sản phẩm thực, hãy triển khai theo thứ tự bảo đảm phiên bản ứng dụng cũ và mới có thể cùng vận hành trong thời gian chuyển đổi.

### 11.3. Hai chế độ `validationLevel`

| `validationLevel` | Document mới | Update document hiện hợp lệ | Update document cũ đang không hợp lệ |
| --- | --- | --- | --- |
| `"strict"` | Kiểm tra | Kiểm tra | Kiểm tra |
| `"moderate"` | Kiểm tra | Kiểm tra | Không kiểm tra theo cùng validator, giúp triển khai dần trên dữ liệu cũ |

`moderate` hữu ích khi collection có document legacy chưa hợp schema mới và bạn chưa thể sửa toàn bộ ngay lập tức. Tuy nhiên, nó **không đảm bảo mọi document cuối cùng đã hợp lệ**; cần kế hoạch làm sạch và chuyển dần về `strict`.

### 11.4. Hai chế độ `validationAction`

| `validationAction` | Khi document không hợp lệ |
| --- | --- |
| `"error"` | Từ chối thao tác ghi và trả lỗi |
| `"warn"` | Cho phép thao tác, ghi cảnh báo về vi phạm vào log MongoDB |

Có thể dùng `warn` trong giai đoạn quan sát để hiểu ứng dụng đang ghi dữ liệu sai ở đâu. Tuy nhiên dữ liệu không hợp lệ vẫn được lưu nếu action này được bật; không nên coi `warn` là thực thi hợp đồng dữ liệu.

Ví dụ đổi tạm sang chế độ cảnh báo:

~~~javascript
labDb.runCommand({
  collMod: "products",
  validationLevel: "strict",
  validationAction: "warn"
});

// Khi đã sẵn sàng từ chối dữ liệu sai:
labDb.runCommand({
  collMod: "products",
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Đoạn này chỉ thay hành vi xử lý vi phạm; validator hiện tại vẫn được giữ. Đối với ứng dụng thật, cần theo dõi log, sửa đường ghi dữ liệu và triển khai chuyển đổi schema có kế hoạch.

## 12. Dữ liệu cũ: kiểm tra trước khi bật `strict + error`

Một điểm quan trọng là **thêm validator không tự động sửa hoặc duyệt lại toàn bộ document đã lưu**. Collection có thể còn những bản ghi không phù hợp schema mới. Với `strict`, các thao tác update tiếp theo trên chúng có thể bị từ chối.

MongoDB cho phép dùng biểu thức `$jsonSchema` trong truy vấn để xác định document nào đạt điều kiện. Có thể dùng `$nor` để tìm document **không đạt** validator:

~~~javascript
const effectiveSchema = labDb
  .getCollectionInfos({ name: "products" })[0]
  .options.validator.$jsonSchema;

labDb.products.find({
  $nor: [
    { $jsonSchema: effectiveSchema }
  ]
});
~~~

Với bộ dữ liệu thực hành chỉ gồm document đã được chấp nhận từ lúc tạo collection, truy vấn này thường không trả về gì. Khi cần đánh giá dữ liệu legacy, hãy chạy cách kiểm tra này **trước** khi chuyển collection sang schema chặt hơn, hoặc trên môi trường thử nghiệm.

Quy trình triển khai hợp lý:

1. **Khảo sát dữ liệu thực:** thu thập BSON type, field bị thiếu, giá trị enum và khoảng số đang tồn tại.
2. **Định nghĩa schema đích:** xác nhận với nghiệp vụ, backend và các luồng import.
3. **Kiểm tra vi phạm:** truy vấn document không đạt schema và thống kê nguyên nhân.
4. **Sửa dữ liệu cũ:** backfill field, sửa enum, chuẩn hóa kiểu số, xử lý giá trị ngoài khoảng.
5. **Cập nhật toàn bộ đường ghi:** API, batch job và công cụ quản trị cùng áp dụng quy ước mới.
6. **Kích hoạt enforcement:** chuyển sang `validationLevel: "strict"` và `validationAction: "error"` khi dữ liệu và client đã sẵn sàng.
7. **Theo dõi lỗi thực tế:** quan sát mã lỗi validation sau khi triển khai và xử lý trường hợp chưa dự kiến.

Nếu cần chuyển đổi dần, có thể sử dụng `warn` hoặc `moderate` theo cách có kiểm soát, nhưng phải có tiêu chí rõ ràng để hoàn tất migration.

## 13. Phân biệt schema validation với các ràng buộc khác

Schema validation rất hữu ích nhưng không thay thế mọi cơ chế đảm bảo dữ liệu:

| Nhu cầu | Schema validation đủ chưa? | Giải pháp bổ sung |
| --- | --- | --- |
| `sku` bắt buộc và đúng định dạng | Có, bằng `required`/`pattern` | Validation UX ở client |
| `status` thuộc danh sách cho phép | Có, bằng `enum` | Kiểm tra chuyển trạng thái nếu có |
| `stock` nằm trong 0–100000 | Có, bằng `minimum`/`maximum` và BSON type | Update atomic khi trừ tồn kho |
| `sku` duy nhất trong collection | Không | **Unique index** |
| Mã danh mục tồn tại trong collection khác | Không có foreign key tự động từ `$jsonSchema` | Logic nghiệp vụ/giao dịch hoặc mô hình dữ liệu phù hợp |
| Chuyển `archived → published` phải được duyệt | Enum không đủ | Điều kiện nghiệp vụ/authorization |
| Chống người dùng không được phép sửa giá | Không | Authentication, authorization, RBAC |
| Kiểm tra định dạng email có thể nhận thư | Regex không đủ | Parser và quy trình xác minh |
| Đơn giá tiền tệ có scale và rounding xác định | Minimum/type không đủ | Quy tắc nghiệp vụ và decimal arithmetic |

Ví dụ uniqueness của SKU:

~~~javascript
labDb.products.createIndex(
  { sku: 1 },
  { unique: true }
);
~~~

Index này cấm hai document có cùng `sku` theo quy tắc so sánh của index, trong khi validator quy định `sku` phải xuất hiện và đúng cấu trúc. **Unique index** và **schema validation** bổ sung cho nhau.

Khi cần chặn stock âm trong thao tác trừ tồn kho đồng thời, nên kết hợp điều kiện atomic:

~~~javascript
const result = labDb.products.updateOne(
  { _id: "P-001", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
);

print(result.modifiedCount);
~~~

Điều kiện lọc đảm bảo chỉ giảm khi tồn kho đủ 2; validator là tầng bảo vệ cuối để giá trị sau ghi không âm. Cần kiểm soát trường hợp `modifiedCount: 0` để trả thông báo hết hàng cho ứng dụng.

## 14. Thực hành: xây dựng validator cho hồ sơ người dùng

Tạo một collection riêng có các quy tắc:

- `username`: bắt buộc, kiểu string, dài từ 4–20 ký tự, chỉ gồm chữ cái Latin không dấu, chữ số và dấu gạch dưới.
- `role`: bắt buộc, thuộc `reader`, `editor`, `admin`.
- `age`: tùy chọn, BSON int32, trong khoảng 0–120.
- `displayName`: tùy chọn, chuỗi dài 1–80 ký tự.
- `score`: tùy chọn, BSON double, trong khoảng 0–100.

Một định nghĩa mẫu:

~~~javascript
labDb.createCollection("profiles", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["username", "role"],
      properties: {
        username: {
          bsonType: "string",
          minLength: 4,
          maxLength: 20,
          pattern: "^[A-Za-z0-9_]+$"
        },
        role: {
          bsonType: "string",
          enum: ["reader", "editor", "admin"]
        },
        age: {
          bsonType: "int",
          minimum: 0,
          maximum: 120
        },
        displayName: {
          bsonType: "string",
          minLength: 1,
          maxLength: 80
        },
        score: {
          bsonType: "double",
          minimum: 0,
          maximum: 100
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Thử một document hợp lệ:

~~~javascript
labDb.profiles.insertOne({
  _id: "U-01",
  username: "user_01",
  role: "reader",
  age: Int32(22),
  displayName: "Nguyễn An",
  score: Double(87.5)
});
~~~

Thử một document không hợp lệ:

~~~javascript
try {
  labDb.profiles.insertOne({
    _id: "U-02",
    username: "ab",     // quá ngắn
    role: "owner",      // ngoài enum
    age: Int32(-5)     // ngoài khoảng
  });
} catch (e) {
  print("Profile không hợp lệ: " + e.message);
}
~~~

Nếu MongoDB trả thông tin chi tiết về validator, bạn có thể quan sát nhiều nhánh thất bại trong cùng một document. Trong sản phẩm thực, cần chuyển kết quả lỗi thành thông báo phù hợp thay vì hiển thị nguyên nội dung lỗi kỹ thuật.

**Bài tập mở rộng:**

1. Thêm `required: ["username", "role", "displayName"]` và thử insert thiếu `displayName`.
2. Cho phép `age` mang giá trị `null` bằng `bsonType: ["int", "null"]`, giữ nguyên `minimum` và `maximum` cho trường hợp là số.
3. Cấm `username` có ký tự khoảng trắng hoặc dấu tiếng Việt theo yêu cầu giả định; giải thích vì sao regex chỉ cho phép ASCII không nên áp dụng bừa bãi cho `displayName`.
4. Tạo unique index trên `username`, thử thêm tài khoản có cùng username nhưng khác `_id`; phân biệt **duplicate key error** với **DocumentValidationFailure**.
5. Đổi `role` để cho phép thêm `"moderator"` bằng `collMod`, rồi thử ghi tài liệu mang vai trò mới.
6. Dùng `$jsonSchema` trong truy vấn để tìm document không đáp ứng quy tắc đã cập nhật.

## 15. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Document failed validation`, mã lỗi 121 | Thiếu field, sai BSON type, enum, range hoặc pattern | Xem chi tiết lỗi và đối chiếu validator |
| Document có field bắt buộc nhưng vẫn bị từ chối | Field bằng `null` hoặc có kiểu sai | Phân biệt `required` với `bsonType` |
| Giá trị số nhìn đúng nhưng bị từ chối | `Int32`, `Long`, `Double` và `Decimal128` là các BSON type khác nhau | Dùng constructor/codec đúng kiểu |
| `"PUBLISHED"` bị từ chối | Enum chỉ khai báo `"published"` | Chuẩn hóa giá trị hoặc sửa contract có kiểm soát |
| Chuỗi dài đúng nhưng bị từ chối | `pattern` không khớp | Kiểm tra dấu neo, bảng ký tự cho phép và escape regex |
| Chuỗi toàn khoảng trắng được chấp nhận | `minLength` không kiểm tra nội dung có nghĩa | Thêm `pattern` phù hợp hoặc chuẩn hóa đầu vào |
| Một số document legacy tồn tại dù trái schema | Validator không tự quét/sửa dữ liệu cũ | Audit và migration, cân nhắc `moderate` |
| Chuyển `strict` khiến update dữ liệu cũ thất bại | Document sau update vẫn không hợp schema | Backfill hoặc chiến lược migration |
| Ghi dữ liệu sai vẫn thành công | `validationAction: "warn"` | Chuyển sang `error` khi đã sẵn sàng |
| Hai document trùng `sku` vẫn được ghi | Schema validation không mặc định đảm bảo unique | Tạo unique index |
| Sửa ứng dụng nhưng validator vẫn cũ | Schema lưu ở collection MongoDB | Sửa bằng `collMod` và phối hợp triển khai |
| Phía API ghi được dữ liệu sai do bypass | Lệnh/client có quyền bypass document validation | Quản lý quyền `bypassDocumentValidation` và policy ghi |

Các thông báo lỗi cụ thể có thể khác nhau theo phiên bản MongoDB và client. Nên quan sát **mã lỗi, namespace, validator hiện tại và thao tác ghi đã gửi** trước khi thay đổi schema.

## 16. Nguyên tắc thiết kế schema validation dễ duy trì

1. **Đặt quy tắc tại đúng cấp object.** `required` của document gốc không tự áp dụng cho object lồng nhau.
2. **Phân biệt tồn tại, kiểu và nội dung.** `required`, `bsonType`, `enum`, `minimum` và `pattern` giải quyết các vấn đề khác nhau.
3. **Kiểm soát BSON type có chủ đích.** Dữ liệu số JavaScript không luôn khớp loại số mà Java/ứng dụng cần.
4. **Chọn regex vừa đủ.** Dùng `^`/`$` khi muốn toàn chuỗi khớp, không biến regex thành bộ kiểm tra tất cả nghiệp vụ phức tạp.
5. **Không xem validator là giải pháp uniqueness hoặc authorization.** Sử dụng index và phân quyền cho các nhiệm vụ tương ứng.
6. **Trước khi làm schema nghiêm ngặt hơn, khảo sát dữ liệu cũ.** Validator mới không tự sửa document legacy.
7. **Quản lý thay đổi schema cùng phiên bản ứng dụng.** Việc thêm enum, đổi giới hạn hoặc đổi BSON type có thể làm client đang chạy ghi thất bại.
8. **Dùng chế độ warn/moderate có thời hạn và mục tiêu.** Mức bảo vệ cuối cùng cho dữ liệu mới thường là `strict` và `error` khi nghiệp vụ yêu cầu enforcement.

Trong MongoDB, schema linh hoạt và schema validation không mâu thuẫn nhau: bạn có thể giữ một số trường tùy chọn, cho phép mở rộng tài liệu, đồng thời quy định chặt những thông tin cốt lõi. Bộ quy tắc **required + enum + khoảng giá trị + quy tắc chuỗi** là nền tảng thực tế để ngăn dữ liệu không nhất quán ngay tại nơi lưu trữ.

### Tài liệu tham khảo chính thức

- [MongoDB Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — giới thiệu cơ chế validation và lợi ích.
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `$jsonSchema`, kiểu BSON và cú pháp validator.
- [JSON Schema Validation](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/) — các keyword và cách dùng `$jsonSchema`.
- [Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — `strict` và `moderate`.
- [Choose How to Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — `error` và `warn`.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — cập nhật validator bằng `collMod`.
