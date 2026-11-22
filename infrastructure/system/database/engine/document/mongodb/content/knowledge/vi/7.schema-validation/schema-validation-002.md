# Khai báo validator với $jsonSchema và bsonType trong MongoDB

MongoDB lưu dữ liệu theo dạng document BSON. Các document trong cùng một collection có thể có những trường và kiểu dữ liệu khác nhau. Sự linh hoạt này hữu ích khi phát triển ứng dụng nhưng cũng tạo rủi ro: một bản ghi có thể lưu **total** dưới dạng chuỗi thay vì số, thiếu **createdAt**, hoặc chứa **status** mà ứng dụng không biết xử lý.

**Schema validation** cho phép khai báo những ràng buộc ngay tại collection. Khi ứng dụng ghi hoặc cập nhật document, MongoDB có thể kiểm tra dữ liệu với **validator** và từ chối thao tác không thỏa điều kiện. Một cách khai báo phổ biến là dùng toán tử **$jsonSchema** cùng từ khóa **bsonType** để mô tả cấu trúc document và các kiểu BSON được chấp nhận.

Bài học này hướng dẫn viết validator từ đơn giản đến lồng nhau, phân biệt **bsonType** với kiểu JSON thông thường, tạo và thay đổi validator, điều khiển mức kiểm tra bằng **validationLevel** và **validationAction**, đồng thời áp dụng trong quy trình phát triển ứng dụng Java.

## 1. Vì sao cần schema validation?

Giả sử một ứng dụng bán hàng lưu document:

~~~javascript
{
  orderCode: "ORD-001",
  status: "NEW",
  total: NumberDecimal("149.90"),
  createdAt: ISODate("2026-11-14T03:00:00Z")
}
~~~

Ứng dụng kỳ vọng:

- **orderCode** là chuỗi không rỗng.
- **status** chỉ nhận một trong các giá trị cho phép.
- **total** là số thập phân Decimal128 và không âm.
- **createdAt** là BSON Date, không phải chuỗi thời gian.

Nếu không có ràng buộc ở database, một chương trình khác vẫn có thể ghi:

~~~javascript
{
  orderCode: "ORD-002",
  status: "UNKNOWN",
  total: "149.90",
  createdAt: "2026-11-14T03:00:00Z"
}
~~~

Đây là document hợp lệ về mặt cấu trúc BSON, nhưng không đúng hợp đồng dữ liệu mà ứng dụng cần. Việc thiếu quy tắc chung có thể khiến truy vấn, tính toán, báo cáo hoặc quá trình đồng bộ giữa các dịch vụ gặp lỗi.

Validator giúp đưa các quy tắc nền tảng đến gần dữ liệu:

~~~text
Frontend / API / Batch job / Script / Java service
                     |
                     | insert / update / replace
                     v
             MongoDB Collection
                     |
              Validator rule
               /          \
           Hợp lệ        Không hợp lệ
              |               |
          Cho ghi        Từ chối ghi hoặc cảnh báo
                        (tùy validationAction)
~~~

Schema validation là **lớp kiểm soát dữ liệu**, không thay thế hoàn toàn validation trong ứng dụng. Ứng dụng vẫn cần kiểm tra dữ liệu đầu vào, thông báo lỗi dễ hiểu, áp dụng quyền nghiệp vụ và quản lý giao dịch.

## 2. Validator, $jsonSchema và bsonType là gì?

| Thành phần | Chức năng | Ví dụ |
|---|---|---|
| **validator** | Tùy chọn của collection chứa biểu thức kiểm tra document | validator: { $jsonSchema: ... } |
| **$jsonSchema** | Toán tử biểu diễn các quy tắc schema theo cú pháp MongoDB hỗ trợ | required, properties, bsonType |
| **bsonType** | Từ khóa khai báo một hoặc nhiều loại dữ liệu BSON được chấp nhận | "string", "int", "date", "objectId" |
| **validationLevel** | Điều khiển document nào được kiểm tra khi ghi | "strict", "moderate", "off" |
| **validationAction** | Quyết định xử lý khi document vi phạm validator | "error", "warn" |

Một validator đơn giản:

~~~javascript
{
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name"],
      properties: {
        name: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  }
}
~~~

Ý nghĩa: document phải là BSON object, có trường **name**, trường này phải là chuỗi và chứa ít nhất một ký tự. Nếu **age** hoặc một trường khác không được mô tả, nó vẫn được phép xuất hiện theo mặc định.

### 2.1. Khác nhau giữa schema và document

Document dữ liệu:

~~~javascript
{
  name: "Lan",
  age: 22
}
~~~

Schema diễn tả quy tắc:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    name: { bsonType: "string" },
    age: { bsonType: "int", minimum: 0 }
  }
}
~~~

**Schema không chứa dữ liệu của một khách hàng cụ thể.** Nó mô tả document nào được chấp nhận. Một schema có thể được áp dụng cho hàng triệu document trong cùng collection.

### 2.2. $jsonSchema không phải toàn bộ tiêu chuẩn JSON Schema

MongoDB hỗ trợ một **tập con các từ khóa của JSON Schema** và bổ sung **bsonType** để phản ánh các kiểu dữ liệu BSON. Không nên sao chép tùy ý một JSON Schema thiết kế cho HTTP API rồi giả định MongoDB sẽ hiểu mọi từ khóa.

Ví dụ những từ khóa quen thuộc của JSON Schema có thể không được hỗ trợ trong MongoDB, hoặc có hành vi phụ thuộc phiên bản. Hãy kiểm tra tài liệu MongoDB đúng phiên bản khi dùng từ khóa ít phổ biến, thay vì cho rằng validator thực thi toàn bộ JSON Schema hiện đại.

Quan trọng hơn, MongoDB kiểm tra **kiểu BSON thực sự lưu trong document**. Một chuỗi trông giống ngày giờ vẫn là BSON String; một chuỗi hex 24 ký tự vẫn là String nếu driver không tạo ObjectId.

## 3. Khai báo validator khi tạo collection

Mở MongoDB Shell (**mongosh**) và chọn database thực hành:

~~~javascript
use validation_lab
~~~

Tạo một collection **orders** với schema kiểm tra bắt buộc:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderCode", "status", "total", "createdAt"],
      properties: {
        _id: {
          bsonType: "objectId"
        },
        orderCode: {
          bsonType: "string",
          minLength: 1
        },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        },
        total: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        createdAt: {
          bsonType: "date"
        }
      },
      additionalProperties: false
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Trong ví dụ:

1. **bsonType: "object"** yêu cầu document gốc là BSON object.
2. **required** quy định bốn trường bắt buộc.
3. **properties** đặt quy tắc cụ thể cho từng trường.
4. **enum** giới hạn status theo tập giá trị.
5. **minimum** không cho phép tổng tiền âm.
6. **additionalProperties: false** từ chối những trường không được mô tả trong properties.
7. **validationLevel: "strict"** áp dụng kiểm tra cho insert và các cập nhật document theo chính sách strict.
8. **validationAction: "error"** từ chối thao tác ghi vi phạm.

Ở đây trường **_id** được khai báo dù không nằm trong **required**. MongoDB thường tự tạo _id kiểu ObjectId nếu document được insert mà không có _id. Khi sử dụng **additionalProperties: false**, cần cho phép _id trong **properties**, nếu không document sẽ bị từ chối vì chứa một trường ngoài danh sách.

Nếu ứng dụng chủ động lưu _id bằng chuỗi hoặc một kiểu BSON khác, hãy điều chỉnh điều kiện _id cho phù hợp. Không phải collection MongoDB nào cũng dùng ObjectId làm _id.

### 3.1. Thử ghi document hợp lệ

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-001",
  status: "NEW",
  total: NumberDecimal("149.90"),
  createdAt: new Date()
})
~~~

MongoDB nhận document, tự tạo _id nếu cần rồi kiểm tra schema. Với cấu hình trên, document hợp lệ vì total là Decimal128, createdAt là Date và các trường còn lại đúng yêu cầu.

Kiểm tra:

~~~javascript
db.orders.findOne({ orderCode: "ORD-001" })
~~~

### 3.2. Thử ghi document sai kiểu

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-002",
  status: "NEW",
  total: "149.90",
  createdAt: new Date()
})
~~~

Thao tác bị từ chối vì **total** là BSON String. Chuỗi "149.90" nhìn giống số tiền nhưng không phải Decimal128; validator không tự ép kiểu theo mong muốn của ứng dụng.

Thử một lỗi khác:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-003",
  status: "SHIPPING",
  total: NumberDecimal("99.00"),
  createdAt: new Date()
})
~~~

Trường status vi phạm **enum** vì schema chỉ cho phép NEW, PAID hoặc CANCELLED.

Thử thiếu trường bắt buộc:

~~~javascript
db.orders.insertOne({
  orderCode: "ORD-004",
  status: "NEW",
  total: NumberDecimal("42.00")
})
~~~

Lần này thiếu **createdAt**, nên document bị từ chối. Schema validation không tự thêm createdAt và cũng không tự tạo giá trị mặc định.

Trong môi trường MongoDB thông thường, lỗi validator có thể xuất hiện với thông báo **Document failed validation**, mã lỗi **121** và, tùy phiên bản/quyền, có chi tiết giải thích trường vi phạm. Đầu ra lỗi có thể khác nhau giữa mongosh và các driver.

## 4. bsonType: phân biệt các kiểu dữ liệu BSON

MongoDB không chỉ có number và string như cách nhìn ở JSON. BSON phân biệt nhiều kiểu số, thời gian, mã định danh và nhị phân.

| Giá trị cần lưu | bsonType | Ví dụ tạo trong mongosh |
|---|---|---|
| Chuỗi | "string" | "MongoDB" |
| Boolean | "bool" | true |
| Object lồng nhau | "object" | { city: "Huế" } |
| Array | "array" | ["A", "B"] |
| Null | "null" | null |
| Số nguyên 32 bit | "int" | NumberInt(12) |
| Số nguyên 64 bit | "long" | NumberLong("9007199254740993") |
| Số thực double | "double" | NumberDouble("3.5") |
| Decimal128 | "decimal" | NumberDecimal("19.90") |
| Mọi kiểu số BSON phổ biến | "number" | Int32, Int64, Double hoặc Decimal128 |
| Thời điểm BSON Date | "date" | ISODate("2026-01-15T08:30:00Z") |
| ObjectId | "objectId" | ObjectId("66f1c2a4b1d2e3f405162738") |
| Binary | "binData" | BinData(0, "AQID") |
| Timestamp | "timestamp" | Timestamp({ t: 1700000000, i: 1 }) |

Tên kiểu BSON trong **bsonType** không nhất thiết giống tên kiểu của ngôn ngữ Java, JavaScript hoặc JSON Schema. Chẳng hạn, **bool** là tên dùng trong bsonType, còn JSON Schema thường nói đến **boolean**.

### 4.1. bsonType: "int" khác "long", "double", "decimal"

Giả sử schema:

~~~javascript
{
  bsonType: "object",
  properties: {
    quantity: {
      bsonType: "int",
      minimum: 0
    }
  }
}
~~~

Schema này **chỉ cho phép BSON Int32** ở trường quantity. Các giá trị cùng ý nghĩa toán học nhưng được lưu dưới dạng Int64, Double hoặc Decimal128 không tự động được xem là Int32.

Ví dụ phân biệt tường minh:

~~~javascript
NumberInt(5)
NumberLong("5")
NumberDouble("5")
NumberDecimal("5")
~~~

Bốn giá trị đều biểu diễn số năm nhưng có kiểu BSON khác nhau. Đây là điểm đặc biệt cần chú ý khi nhiều ứng dụng Java, JavaScript, Python hoặc công cụ import cùng ghi vào một collection.

Nếu muốn chấp nhận nhiều kiểu số mà vẫn không chấp nhận String:

~~~javascript
{
  bsonType: "number",
  minimum: 0
}
~~~

Hoặc khai báo cụ thể những loại số được chấp nhận:

~~~javascript
{
  bsonType: ["int", "long"],
  minimum: 0
}
~~~

Lựa chọn phụ thuộc hợp đồng dữ liệu:

- **int:** phù hợp khi toàn hệ thống thống nhất dùng số nguyên 32 bit cho một trường.
- **long:** phù hợp với bộ đếm hoặc mã số nguyên 64 bit.
- **decimal:** phù hợp với giá trị cần độ chính xác thập phân, ví dụ tiền theo quy tắc nghiệp vụ.
- **number:** phù hợp khi cần nhận nhiều kiểu số BSON, nhưng ít chặt chẽ hơn về loại lưu trữ.

Không nên chỉ vì một giá trị nhìn giống số trên màn hình mà kết luận nó có kiểu BSON đúng với schema.

### 4.2. bsonType: "date" không chấp nhận chuỗi ISO

Ví dụ:

~~~javascript
{
  properties: {
    createdAt: {
      bsonType: "date"
    }
  }
}
~~~

Được chấp nhận:

~~~javascript
{ createdAt: ISODate("2026-01-15T08:30:00Z") }
~~~

Không được chấp nhận:

~~~javascript
{ createdAt: "2026-01-15T08:30:00Z" }
~~~

Vế sau là BSON String, dù có định dạng thời gian ISO-8601. Trong ứng dụng Java, hãy ánh xạ kiểu ngày phù hợp qua MongoDB codec; trong mongosh, dùng Date/ISODate thay vì chỉ gửi chuỗi.

### 4.3. bsonType: "objectId" không chấp nhận chuỗi hex

~~~javascript
{
  properties: {
    customerId: {
      bsonType: "objectId"
    }
  }
}
~~~

Được chấp nhận:

~~~javascript
{ customerId: ObjectId("66f1c2a4b1d2e3f405162738") }
~~~

Không được chấp nhận:

~~~javascript
{ customerId: "66f1c2a4b1d2e3f405162738" }
~~~

Chuyển chuỗi hex thành ObjectId phải do ứng dụng hoặc driver thực hiện theo quy tắc dữ liệu. Validator chỉ kiểm tra kiểu của giá trị đã được gửi đến MongoDB.

### 4.4. bsonType trong mảng

Một trường có thể cho phép nhiều kiểu BSON:

~~~javascript
{
  properties: {
    nickname: {
      bsonType: ["string", "null"]
    }
  }
}
~~~

Với quy tắc này:

- **nickname: "Na"** hợp lệ.
- **nickname: null** hợp lệ.
- Không có trường **nickname** cũng hợp lệ, vì không được đưa vào required.
- **nickname: 123** không hợp lệ.

Điều này cho thấy **required** và **bsonType** là hai quy tắc độc lập: một quy định sự hiện diện của trường, quy tắc kia kiểm tra giá trị khi trường xuất hiện.

## 5. required và properties: bắt buộc có trường, nhưng vẫn cần kiểm tra giá trị

Xét schema:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    name: { bsonType: "string" },
    age: { bsonType: "int", minimum: 0 }
  }
}
~~~

| Document | Hợp lệ? | Lý do |
|---|---|---|
| { name: "An" } | Có | name có mặt và đúng kiểu; age là trường tùy chọn |
| { name: "An", age: NumberInt(20) } | Có | age thuộc kiểu Int32 và không âm |
| { age: NumberInt(20) } | Không | Thiếu name trong required |
| { name: 99 } | Không | name có mặt nhưng sai kiểu string |
| { name: "", age: NumberInt(20) } | Có | Chuỗi rỗng vẫn là string nếu không có minLength |
| { name: "An", age: null } | Không | null không thuộc bsonType int |

Muốn ngăn chuỗi rỗng:

~~~javascript
name: {
  bsonType: "string",
  minLength: 1
}
~~~

Nếu muốn bỏ qua chuỗi chỉ chứa khoảng trắng, có thể thêm **pattern** phù hợp hoặc kiểm tra nội dung đã chuẩn hóa tại ứng dụng. Ví dụ minLength: 1 không tự loại bỏ chuỗi "   ".

### 5.1. Trường bắt buộc có được phép là null không?

Có, nếu schema cho phép giá trị null:

~~~javascript
{
  required: ["notes"],
  properties: {
    notes: {
      bsonType: ["string", "null"]
    }
  }
}
~~~

Document **{ notes: null }** thỏa quy tắc required và bsonType. Document **{}** không thỏa required. Nếu nghiệp vụ muốn notes là chuỗi có nội dung, cần dùng bsonType: "string" cùng điều kiện về độ dài/pattern.

### 5.2. Không khai báo required thì điều gì xảy ra?

Nếu chỉ viết:

~~~javascript
{
  properties: {
    email: {
      bsonType: "string",
      pattern: "^[^@ ]+@[^@ ]+$"
    }
  }
}
~~~

Document thiếu **email** vẫn hợp lệ, vì properties chỉ kiểm tra email **nếu trường xuất hiện**. Đây là nguyên nhân phổ biến khiến một schema có vẻ chặt chẽ nhưng vẫn nhận document thiếu dữ liệu.

## 6. Đóng schema bằng additionalProperties

Mặc định, schema chỉ giới hạn những trường đã khai báo; document có thể chứa thêm trường khác nếu không có quy tắc cấm. Ví dụ:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    name: { bsonType: "string" }
  }
}
~~~

Vẫn có thể chấp nhận:

~~~javascript
{
  name: "An",
  unexpectedField: 123
}
~~~

Nếu muốn không nhận trường ngoài danh sách:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  properties: {
    _id: { bsonType: "objectId" },
    name: { bsonType: "string" }
  },
  additionalProperties: false
}
~~~

Lúc này **unexpectedField** bị từ chối. Trường **_id** được khai báo để tương thích với document MongoDB thường có _id; nếu ứng dụng dùng kiểu _id khác ObjectId thì phải chỉnh điều kiện tương ứng.

**Cân nhắc khi dùng additionalProperties: false:**

- Ưu điểm: bắt lỗi gõ nhầm tên trường, ngăn dữ liệu thừa ngoài hợp đồng.
- Hạn chế: mỗi khi phát triển thêm trường mới, cần cập nhật validator có kiểm soát.
- Với document lồng nhau, **additionalProperties** cần được đặt tại đúng cấp object mà bạn muốn giới hạn. Đóng schema ở cấp ngoài không tự đóng mọi object bên trong nếu schema con chưa khai báo quy tắc tương ứng.

Đối với các bản ghi có nhiều metadata động, có thể chủ động cho phép một trường **metadata** kiểu object thay vì mở tự do mọi trường gốc.

## 7. Ràng buộc chuỗi, số và tập giá trị

Ngoài bsonType, $jsonSchema hỗ trợ các từ khóa kiểm tra nội dung thường dùng.

### 7.1. Chuỗi: minLength, maxLength và pattern

~~~javascript
{
  bsonType: "string",
  minLength: 3,
  maxLength: 20,
  pattern: "^[A-Z0-9-]+$"
}
~~~

Ví dụ này yêu cầu một mã gồm 3–20 ký tự, chỉ nhận chữ cái ASCII in hoa, chữ số hoặc dấu gạch ngang.

Một số giá trị:

| Giá trị | Kết quả | Lý do |
|---|---|---|
| "ORD-1001" | Hợp lệ | Đúng độ dài và pattern |
| "ab-01" | Không hợp lệ | Có chữ thường |
| "A" | Không hợp lệ | Ngắn hơn minLength |
| 1001 | Không hợp lệ | Không phải BSON String |

**Pattern** là biểu thức chính quy. Hãy giữ quy tắc đơn giản và kiểm tra với dữ liệu thực tế, đặc biệt khi chuỗi có Unicode hoặc cần các ràng buộc phức tạp như email quốc tế. Regex đơn giản không thay thế được một bộ kiểm tra nghiệp vụ đầy đủ.

### 7.2. Số: minimum, maximum, multipleOf

~~~javascript
{
  bsonType: "int",
  minimum: 1,
  maximum: 100
}
~~~

Quy tắc phù hợp cho số lượng từ 1 đến 100, nếu ứng dụng lưu nhất quán dưới dạng Int32.

Ví dụ giới hạn giá trị không âm:

~~~javascript
{
  bsonType: "decimal",
  minimum: NumberDecimal("0")
}
~~~

MongoDB hỗ trợ những điều kiện như **minimum**, **maximum** và **multipleOf** trong phạm vi JSON Schema mà nó triển khai. Khi kiểm tra tiền, không nên dựa duy nhất vào kiểu số; ứng dụng vẫn cần quy tắc làm tròn, đơn vị tiền tệ và phạm vi hợp lệ.

### 7.3. enum: giới hạn các giá trị cụ thể

~~~javascript
{
  enum: ["PENDING", "PAID", "CANCELLED"]
}
~~~

Một trường status thường phù hợp với **enum**. Các giá trị phải đúng cả nội dung và kiểu dữ liệu. Nếu status là trạng thái thay đổi theo luồng nghiệp vụ, enum chỉ hạn chế **tập trạng thái có thể lưu**, không bảo đảm mọi phép chuyển trạng thái đều đúng.

Ví dụ, enum không ngăn tự động việc chuyển từ CANCELLED về PAID. Quy tắc chuyển trạng thái cần được kiểm soát ở ứng dụng hoặc trong điều kiện cập nhật có tính đến trạng thái hiện hành.

## 8. Document lồng nhau: properties và required ở từng cấp

Document MongoDB thường chứa object bên trong object. Ví dụ đơn hàng:

~~~javascript
{
  orderCode: "ORD-010",
  shippingAddress: {
    recipient: "Lan",
    city: "Hà Nội",
    postalCode: "100000"
  }
}
~~~

Để kiểm tra shippingAddress, khai báo **bsonType: "object"** rồi lồng tiếp **required**, **properties**:

~~~javascript
{
  bsonType: "object",
  required: ["orderCode", "shippingAddress"],
  properties: {
    orderCode: {
      bsonType: "string",
      minLength: 1
    },
    shippingAddress: {
      bsonType: "object",
      required: ["recipient", "city"],
      properties: {
        recipient: {
          bsonType: "string",
          minLength: 1
        },
        city: {
          bsonType: "string",
          minLength: 1
        },
        postalCode: {
          bsonType: "string"
        }
      }
    }
  }
}
~~~

Ở đây:

- Document gốc bắt buộc có shippingAddress.
- shippingAddress phải là object, không phải string hoặc array.
- Bên trong shippingAddress, **recipient** và **city** là bắt buộc.
- **postalCode** tùy chọn.

**required ở cấp ngoài không tự động áp dụng xuống object con.** Mỗi object cần đặt quy tắc required riêng khi muốn bắt buộc trường con.

### 8.1. Nếu field con có thể vắng mặt?

Nếu shippingAddress không nằm trong required ở cấp ngoài, document chưa có địa chỉ vẫn được nhận. Nhưng khi shippingAddress xuất hiện, những ràng buộc khai báo bên dưới nó vẫn được áp dụng.

Nếu shippingAddress có thể là null, cần khai báo bsonType cho phép null và cân nhắc logic validation khác cho cấu trúc con. Đừng nhầm trường tùy chọn với trường có giá trị null.

## 9. Array: items, minItems, maxItems và uniqueItems

Một đơn hàng có danh sách sản phẩm:

~~~javascript
{
  items: [
    { sku: "PEN-01", quantity: NumberInt(2) },
    { sku: "BOOK-02", quantity: NumberInt(1) }
  ]
}
~~~

Schema có thể kiểm tra kiểu array và các phần tử:

~~~javascript
{
  bsonType: "array",
  minItems: 1,
  maxItems: 50,
  items: {
    bsonType: "object",
    required: ["sku", "quantity"],
    properties: {
      sku: {
        bsonType: "string",
        minLength: 1
      },
      quantity: {
        bsonType: "int",
        minimum: 1
      }
    },
    additionalProperties: false
  }
}
~~~

Ý nghĩa:

- items phải là BSON Array.
- Array cần có ít nhất một phần tử và tối đa 50 phần tử.
- Mỗi phần tử phải là object.
- Mỗi object phải có sku và quantity đúng kiểu.
- Mỗi phần tử không được chứa trường ngoài sku và quantity.

Điều kiện **uniqueItems: true** có thể dùng để yêu cầu các phần tử array không trùng nhau theo quy tắc so sánh giá trị. Tuy nhiên, nó **không thay thế quy tắc duy nhất theo riêng một field của object**. Ví dụ hai object có sku giống nhau nhưng quantity khác nhau vẫn là hai object khác nhau; nếu nghiệp vụ yêu cầu mỗi sku chỉ xuất hiện một lần trong array, nên xử lý riêng quy tắc này.

## 10. Một validator đầy đủ cho collection sản phẩm

Sau khi hiểu từng phần, ta kết hợp vào một ví dụ có thể chạy bằng mongosh. Chọn database thực hành:

~~~javascript
use validation_lab
~~~

Tạo collection **products**:

~~~javascript
db.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "name", "price", "stock", "createdAt"],
      additionalProperties: false,
      properties: {
        _id: {
          bsonType: "objectId"
        },
        sku: {
          bsonType: "string",
          minLength: 3,
          maxLength: 30,
          pattern: "^[A-Z0-9-]+$"
        },
        name: {
          bsonType: "string",
          minLength: 1,
          maxLength: 150
        },
        price: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        stock: {
          bsonType: "int",
          minimum: 0
        },
        active: {
          bsonType: "bool"
        },
        createdAt: {
          bsonType: "date"
        },
        tags: {
          bsonType: "array",
          maxItems: 20,
          items: {
            bsonType: "string",
            minLength: 1
          }
        },
        dimensions: {
          bsonType: "object",
          required: ["width", "height"],
          additionalProperties: false,
          properties: {
            width: {
              bsonType: "number",
              minimum: 0
            },
            height: {
              bsonType: "number",
              minimum: 0
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Một số quyết định thiết kế trong ví dụ:

- **sku** chỉ có ký tự phù hợp quy tắc mã sản phẩm.
- **price** lưu Decimal128 thay vì nhận mọi kiểu số.
- **stock** phải là Int32 không âm.
- **active**, **tags**, **dimensions** là trường tùy chọn; nếu có thì phải đúng kiểu.
- **dimensions** là object lồng nhau chỉ có width và height.
- **_id** được cho phép bởi additionalProperties: false, nhưng không bắt buộc truyền ở insert vì MongoDB có thể tự tạo.

### 10.1. Thêm sản phẩm hợp lệ

~~~javascript
db.products.insertOne({
  sku: "PEN-001",
  name: "Bút bi xanh",
  price: NumberDecimal("12500.00"),
  stock: NumberInt(120),
  active: true,
  createdAt: new Date(),
  tags: ["stationery", "blue"],
  dimensions: {
    width: 1.1,
    height: 14.0
  }
})
~~~

Giá trị width/height được nhận vì schema cho phép **bsonType: "number"**. Trường price và stock được tạo bằng helper rõ kiểu để tránh khác biệt cách ngôn ngữ hoặc driver suy luận literal số.

### 10.2. Thêm sản phẩm sai nhiều điều kiện

~~~javascript
db.products.insertOne({
  sku: "pen 002",
  name: "",
  price: NumberDouble("12500.0"),
  stock: NumberInt(-5),
  createdAt: "2026-11-14T03:00:00Z",
  unknownField: true
})
~~~

Document này vi phạm nhiều quy tắc:

1. sku có chữ thường và dấu cách không thỏa pattern.
2. name là chuỗi rỗng, vi phạm minLength.
3. price là Double thay vì Decimal128.
4. stock nhỏ hơn 0.
5. createdAt là String thay vì Date.
6. unknownField không được phép do additionalProperties: false.

Với validationAction: "error", thao tác ghi bị từ chối. Thông thường, ứng dụng nên báo rõ lỗi nhập liệu cho người dùng trước khi gửi document tới MongoDB.

### 10.3. Tạo unique index cho sku

Validator ở trên **không bảo đảm sku duy nhất giữa các document**. Nếu hai document cùng sku nhưng khác _id đều thỏa schema, validator không tự chặn sự trùng lặp liên document.

Ràng buộc duy nhất cần dùng index:

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true }
)
~~~

Đây là minh họa rõ ràng về ranh giới:

| Yêu cầu | Cơ chế phù hợp |
|---|---|
| sku phải là chuỗi đúng pattern | $jsonSchema |
| price phải là Decimal128 không âm | $jsonSchema |
| stock phải là Int32 không âm | $jsonSchema |
| Mỗi sku chỉ xuất hiện một lần trong collection | Unique index |
| Người dùng A có quyền sửa sản phẩm nào | Authorization/điều kiện nghiệp vụ |
| Chuyển trạng thái đơn hàng đúng quy trình | Logic nghiệp vụ, điều kiện cập nhật hoặc transaction thích hợp |

Đừng đặt kỳ vọng rằng một schema document có thể thay thế tất cả các ràng buộc liên document hoặc quy tắc nghiệp vụ.

## 11. Cập nhật validator của collection đã tồn tại bằng collMod

**db.createCollection()** phù hợp khi tạo collection mới. Nếu collection đã tồn tại, muốn sửa validator hoặc tùy chọn validation, dùng lệnh **collMod** trong các trường hợp được hỗ trợ.

Ví dụ collection **legacyUsers** đã có dữ liệu:

~~~javascript
db.legacyUsers.insertMany([
  { name: "An", age: NumberInt(20) },
  { name: "Bình", age: NumberInt(30) }
])
~~~

Đặt validator:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name"],
      properties: {
        name: {
          bsonType: "string",
          minLength: 1
        },
        age: {
          bsonType: "int",
          minimum: 0
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Lệnh collMod cập nhật quy tắc dùng cho các thao tác ghi sau đó. **Việc khai báo validator không tự sửa, không xóa và không tự chuyển kiểu các document đã tồn tại**.

Nếu collection đã có record sai, chúng vẫn có thể ở trong database sau khi thay đổi schema. Điều kiện strict có ảnh hưởng khi các document đó được cập nhật, vì vậy cần kế hoạch đánh giá dữ liệu trước khi kích hoạt kiểm tra chặt.

### 11.1. Chỉ thay đổi cách xử lý vi phạm

Có thể thay đổi validationAction mà không cần khai báo lại toàn bộ schema:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "warn"
})
~~~

Hoặc đưa về từ chối ghi:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "error"
})
~~~

Trong tình huống migration, thay đổi từng tùy chọn có kiểm soát giúp hạn chế nguy cơ vô tình thay thế một validator phức tạp bằng bản đơn giản hơn.

### 11.2. Xem validator hiện đang được lưu

~~~javascript
db.getCollectionInfos({ name: "legacyUsers" })
~~~

Kết quả bao gồm metadata collection và các tùy chọn đã được lưu, như validator hoặc validationLevel/validationAction nếu có. Tùy phiên bản MongoDB, cách hiển thị metadata có thể khác nhau; hãy tập trung vào **options** của collection đúng tên.

Có thể kiểm tra danh sách collection:

~~~javascript
db.getCollectionNames()
~~~

Nếu cần kiểm tra trong ứng dụng quản trị, hãy xác nhận quyền đọc metadata phù hợp. Đừng giả định collection đã được tạo đúng chỉ vì tên của nó tồn tại.

## 12. validationLevel: strict, moderate và off

**validationLevel** xác định MongoDB thực hiện kiểm tra với phạm vi nào khi document được ghi hoặc cập nhật.

| validationLevel | Insert mới | Update document vốn hợp lệ | Update document vốn không hợp lệ | Ý nghĩa |
|---|---|---|---|---|
| **strict** | Kiểm tra | Kiểm tra | Kiểm tra | Chế độ kiểm tra chặt cho các thao tác ghi |
| **moderate** | Kiểm tra | Kiểm tra | Không áp dụng kiểm tra theo cách strict | Hỗ trợ chuyển đổi dần khi collection đã có dữ liệu cũ sai schema |
| **off** | Không kiểm tra | Không kiểm tra | Không kiểm tra | Tắt thực thi validator |

Điểm cần nhớ: **moderate** vẫn kiểm tra document mới. Nó cũng kiểm tra cập nhật đối với document hiện tại đang hợp lệ, nhưng cho phép những record lịch sử đã không hợp lệ được cập nhật mà không phải thỏa toàn bộ schema ngay.

Ví dụ trong collection có document cũ:

~~~javascript
{
  name: 123,
  age: NumberInt(25)
}
~~~

Schema mới yêu cầu name là String. Với **strict**, một cập nhật lên document trên có thể bị từ chối nếu trạng thái document sau cập nhật vẫn vi phạm validator. Với **moderate**, MongoDB không áp dụng validator cho cập nhật lên document vốn đã sai schema ở thời điểm được xét.

### 12.1. Vì sao cần hiểu moderate?

Moderate có ích khi phải triển khai schema mới cho collection lâu đời mà chưa thể sửa toàn bộ dữ liệu trong một lần. Tuy nhiên, nó cũng có nghĩa document sai schema **có thể tiếp tục tồn tại hoặc bị cập nhật mà vẫn sai**.

Vì vậy, moderate nên được sử dụng như một bước chuyển đổi có chủ đích, không phải cách để mặc định bỏ qua các sai phạm mãi mãi.

### 12.2. Thay đổi mức validation

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationLevel: "moderate"
})
~~~

Khi đã làm sạch dữ liệu cũ và cập nhật toàn bộ ứng dụng ghi:

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationLevel: "strict"
})
~~~

Chuyển từ moderate sang strict không tự động kiểm tra lại và sửa tất cả document cũ ngay tại thời điểm thực thi collMod. Việc kiểm tra tập dữ liệu hiện có là một bước riêng.

## 13. validationAction: error và warn

**validationAction** xác định MongoDB phản ứng thế nào khi thao tác ghi vi phạm validator (với những document thuộc phạm vi kiểm tra theo validationLevel).

### 13.1. error: từ chối document vi phạm

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "error"
})
~~~

Đây là lựa chọn khi quy tắc đã ổn định và ứng dụng cần dữ liệu mới phải đáp ứng schema. Một document vi phạm có thể gây lỗi **Document failed validation** thay vì được lưu.

Ứng dụng Java cần bắt lỗi từ driver và ánh xạ nó thành thông báo thích hợp, tránh lộ toàn bộ cấu trúc nội bộ của database ra client.

### 13.2. warn: ghi cảnh báo nhưng vẫn cho phép

~~~javascript
db.runCommand({
  collMod: "legacyUsers",
  validationAction: "warn"
})
~~~

Ở chế độ này, MongoDB có thể ghi nhận vi phạm trong log, nhưng vẫn **cho phép thao tác ghi tiếp tục**. Điều đó hữu ích để quan sát mức độ vi phạm trước khi bật từ chối, đặc biệt khi nhiều ứng dụng cũ cùng ghi vào database.

**Warn không phải cơ chế bảo vệ toàn vẹn dữ liệu.** Dữ liệu vi phạm vẫn có thể được lưu; nếu hệ thống cần ràng buộc bắt buộc, cần quay về error sau khi đã xử lý các nguồn ghi không đúng.

### 13.3. Kết hợp validationLevel và validationAction

Hai tùy chọn giải quyết hai câu hỏi khác nhau:

~~~text
validationLevel:
    "Document nào sẽ được kiểm tra?"

validationAction:
    "Khi một document được kiểm tra và vi phạm,
     MongoDB sẽ làm gì?"
~~~

Ví dụ:

| Level | Action | Kết quả đặc trưng |
|---|---|---|
| strict | error | Kiểm tra mọi insert/update liên quan và từ chối vi phạm |
| strict | warn | Kiểm tra rộng, ghi cảnh báo nhưng không chặn ghi |
| moderate | error | Chặn insert sai và cập nhật sai trên document vốn hợp lệ; cho phép chuyển đổi dần dữ liệu lịch sử sai |
| moderate | warn | Quan sát vi phạm trong phạm vi kiểm tra của moderate, không chặn ghi |
| off | error hoặc warn | Validator không được áp dụng nên action không tạo hiệu lực kiểm tra trong chế độ off |

Các phiên bản MongoDB mới có thể bổ sung lựa chọn hành động khác; khi triển khai cần đối chiếu đúng phiên bản server. Những ví dụ ở đây sử dụng hai chế độ phổ biến là **error** và **warn**.

## 14. Validator áp dụng khi update như thế nào?

Schema validation không chỉ dành cho insert. Khi một update làm document sau cập nhật vi phạm schema, MongoDB có thể từ chối thao tác nếu validationLevel/action đang yêu cầu kiểm tra và chặn.

Giả sử products có stock kiểu Int32:

~~~javascript
db.products.updateOne(
  { sku: "PEN-001" },
  { $set: { stock: NumberInt(95) } }
)
~~~

Thao tác này hợp lệ. Nhưng:

~~~javascript
db.products.updateOne(
  { sku: "PEN-001" },
  { $set: { stock: "ninety-five" } }
)
~~~

Không hợp lệ vì stock trở thành String.

Tương tự:

~~~javascript
db.products.updateOne(
  { sku: "PEN-001" },
  { $unset: { createdAt: "" } }
)
~~~

Sẽ vi phạm vì createdAt nằm trong **required**. MongoDB kiểm tra trạng thái document theo kết quả cập nhật, chứ không chỉ nhìn tên toán tử $set hay $unset.

### 14.1. Upsert có cần thỏa validator không?

Có. Upsert có thể tạo document mới nếu không tìm thấy record phù hợp. Document mới đó phải đáp ứng validator khi validationLevel đang bật:

~~~javascript
db.products.updateOne(
  { sku: "BOOK-001" },
  {
    $setOnInsert: {
      name: "Sổ tay",
      price: NumberDecimal("25000.00"),
      stock: NumberInt(10),
      createdAt: new Date()
    }
  },
  { upsert: true }
)
~~~

Nếu record chưa tồn tại, các trường từ điều kiện và $setOnInsert tạo nên document mới; chúng phải thỏa schema. Đừng mặc định rằng thao tác upsert được miễn kiểm tra vì API sử dụng updateOne.

### 14.2. Bulk write và transaction

Các thao tác ghi hàng loạt hoặc ghi trong transaction cũng chịu ảnh hưởng từ validator. Khi một thao tác ghi vi phạm, hành vi báo lỗi và mức độ tiếp tục của batch phụ thuộc API, chế độ ordered/unordered và ngữ cảnh transaction. Ứng dụng cần xử lý lỗi theo hợp đồng của driver và không giả định toàn bộ batch sẽ được lưu nếu có document không hợp lệ.

## 15. Dữ liệu cũ: kiểm tra, sửa và triển khai validator an toàn

Đặt validator lên collection đang có nhiều dữ liệu cần một chiến lược migration. **Thêm validator không đồng nghĩa với việc collection hiện tại đã sạch.**

Một quy trình thường dùng:

1. Xác định schema đích từ hợp đồng nghiệp vụ và kiểu BSON thực tế.
2. Kiểm kê document cũ; xác định các nhóm thiếu trường, sai kiểu, trùng mã, giá trị không hợp lệ.
3. Chuẩn hóa code ghi của các ứng dụng/worker để tạo đúng kiểu dữ liệu.
4. Triển khai validator ở chế độ quan sát khi phù hợp, chẳng hạn strict + warn.
5. Sửa dữ liệu cũ bằng migration có khả năng chạy lại và có phương án rollback/backup.
6. Bật strict + error khi tập dữ liệu và các nguồn ghi đã đáp ứng điều kiện.
7. Theo dõi lỗi ghi sau triển khai để phát hiện client còn dùng schema cũ.

### 15.1. Tìm document chưa phù hợp với schema

Ngoài công dụng làm validator, toán tử **$jsonSchema** có thể dùng trong bộ lọc truy vấn. Ví dụ schema kiểm tra name và age:

~~~javascript
const userRules = {
  bsonType: "object",
  required: ["name"],
  properties: {
    name: {
      bsonType: "string",
      minLength: 1
    },
    age: {
      bsonType: "int",
      minimum: 0
    }
  }
};

// Các document thỏa schema
db.legacyUsers.find({
  $jsonSchema: userRules
});

// Các document không thỏa schema
db.legacyUsers.find({
  $nor: [
    { $jsonSchema: userRules }
  ]
}).limit(20);
~~~

Cách này hữu ích để khảo sát dữ liệu cũ. Với collection lớn, truy vấn kiểm tra schema có thể tốn chi phí; nên chạy theo kế hoạch kiểm kê phù hợp thay vì quét toàn bộ dữ liệu nhạy cảm lúc hệ thống tải cao.

### 15.2. Không tự động chuyển kiểu trong validator

Nếu có record:

~~~javascript
{
  name: "An",
  age: "25"
}
~~~

Schema **bsonType: "int"** không tự biến chuỗi "25" thành Int32. Việc chuyển đổi là trách nhiệm của migration hoặc ứng dụng, ví dụ sau khi xác minh giá trị nhập có thể chuyển an toàn sang số nguyên.

Không nên chuyển bừa mọi chuỗi sang số hoặc ngày: "00123" có thể là mã định danh cần giữ số 0 đầu, còn ngày không kèm múi giờ có thể gây sai nghĩa.

### 15.3. Schema evolution khi thêm một trường mới

Giả sử products cần thêm **category**. Nếu muốn field đó trở thành bắt buộc, thường cần xử lý theo trình tự:

~~~text
Giai đoạn 1: Ứng dụng mới bắt đầu ghi category
Giai đoạn 2: Dữ liệu cũ được backfill category thích hợp
Giai đoạn 3: Kiểm tra record còn thiếu hoặc sai kiểu
Giai đoạn 4: Validator thêm category vào required
Giai đoạn 5: Theo dõi ghi lỗi sau triển khai
~~~

Nếu thêm category vào required ngay khi các client cũ còn ghi thiếu trường hoặc khi nhiều document cũ chưa được cập nhật, có thể gây lỗi update ngoài ý muốn ở chế độ strict.

## 16. Tại sao validator không thay thế validation ở ứng dụng Java?

Một API nhận dữ liệu từ HTTP có thể dùng DTO, Jakarta Bean Validation và kiểm tra nghiệp vụ trước khi tạo document MongoDB. Ví dụ ý tưởng:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.math.BigDecimal;

public record CreateProductRequest(
        @NotBlank String sku,
        @NotBlank String name,
        @NotNull @PositiveOrZero BigDecimal price,
        @NotNull @PositiveOrZero Integer stock
) {
}
~~~

Đây là kiểm tra ở lớp ứng dụng: giúp phản hồi sớm cho người dùng trước khi truy cập database. Khi ánh xạ tới MongoDB, ứng dụng còn phải quyết định:

- BigDecimal được lưu thành **Decimal128** nếu schema yêu cầu bsonType: "decimal".
- Integer được lưu thành **Int32** khi codec/mapping của driver phù hợp với mong muốn.
- Thời gian tạo được lưu thành **BSON Date** chứ không phải chuỗi.
- Các trường chỉ do server quyết định, như _id hoặc createdAt, không nên tin hoàn toàn dữ liệu tự khai báo từ client.

Ví dụ Java MongoDB Sync Driver tạo giá trị có kiểu tường minh:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.util.Date;

public class InsertValidatedProduct {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Document product = new Document("sku", "PEN-JAVA-01")
                .append("name", "Bút Java")
                .append("price", new Decimal128(new BigDecimal("12500.00")))
                .append("stock", 12)
                .append("createdAt", new Date());

        try (MongoClient client = MongoClients.create(uri)) {
            client.getDatabase("validation_lab")
                    .getCollection("products")
                    .insertOne(product);
        }
    }
}
~~~

Đoạn code minh họa việc tạo **Decimal128**, **Int32** (Integer Java được BSON codec thông thường mã hóa tương ứng) và **Date**. Nó cần thư viện mongodb-driver-sync tương thích và collection **products** đã được tạo với validator phù hợp.

### 16.1. Validator được kiểm tra ở database

Nếu ứng dụng Java dùng MongoRepository hoặc MongoTemplate, phần ánh xạ object của Spring Data MongoDB tạo document BSON thông qua cơ chế mapping. Validator vẫn được MongoDB thực thi ở collection theo cấu hình, không phụ thuộc bạn gọi insert từ mongosh, Java driver hay một dịch vụ khác.

Lợi ích là có một tầng ràng buộc chung cho nhiều nguồn ghi. Dù vậy, mọi nguồn ghi cần được thiết kế để gửi **đúng BSON type**, không chỉ đúng hình thức JSON.

### 16.2. Xử lý DocumentValidationFailure

Khi bị từ chối do schema, driver ném ngoại lệ ghi có thông tin từ MongoDB. Ứng dụng nên:

1. Ghi log nội bộ có ngữ cảnh nhưng che thông tin nhạy cảm.
2. Trả lỗi nhập liệu hoặc lỗi xử lý dữ liệu phù hợp với API.
3. Không tự động retry vô hạn một document vẫn sai schema.
4. Theo dõi lỗi theo collection và nguồn ghi để sửa hợp đồng dữ liệu.

Không nên gửi nguyên lỗi database hoặc nguyên nội dung document chứa thông tin cá nhân về frontend chỉ để hiển thị lý do validation.

## 17. Validator không giải quyết những yêu cầu nào?

Schema validation rất hữu ích nhưng có phạm vi nhất định.

| Yêu cầu | $jsonSchema có giải quyết đầy đủ? | Cơ chế bổ sung |
|---|---|---|
| Kiểm tra field bắt buộc | Có | required |
| Kiểm tra kiểu BSON | Có | bsonType |
| Chuỗi phải khớp pattern | Có trong phạm vi hỗ trợ | pattern |
| Một số phải nằm trong miền hợp lệ | Có | minimum, maximum |
| Danh sách phải có số phần tử phù hợp | Có | minItems, maxItems |
| sku duy nhất trong toàn bộ collection | Không | Unique index |
| customerId trỏ đến khách hàng tồn tại | Không tự bảo đảm | Kiểm tra nghiệp vụ hoặc mô hình dữ liệu phù hợp |
| User có quyền thay đổi document nào | Không | Authorization, điều kiện truy vấn |
| Trạng thái chuyển đúng qua từng bước | Không đầy đủ bằng enum | Quy tắc nghiệp vụ và cập nhật có điều kiện |
| Tự tạo trường default | Không | Code ứng dụng hoặc quy trình ghi |
| Tự sửa document đã lưu trước khi thêm schema | Không | Migration |
| Mã hóa, bảo mật và kiểm soát truy cập | Không | Cơ chế bảo mật MongoDB và ứng dụng |

Một số ràng buộc liên field có thể biểu diễn bằng các toán tử validator phù hợp ngoài $jsonSchema, nhưng nên giữ quy tắc rõ ràng, có thể vận hành và tránh biến database validator thành nơi chứa toàn bộ logic nghiệp vụ phức tạp.

## 18. Vận hành, quyền và lỗi thường gặp

### 18.1. Bypass document validation

MongoDB có khả năng **bypassDocumentValidation** ở một số thao tác ghi khi client có quyền phù hợp. Đây là cơ chế quản trị hoặc migration đặc biệt; không nên coi validator là lớp kiểm soát tuyệt đối nếu có tài khoản được phép bỏ qua nó.

Ví dụ minh họa lệnh insert ở cấp command:

~~~javascript
db.runCommand({
  insert: "legacyUsers",
  documents: [
    { name: 123 }
  ],
  bypassDocumentValidation: true
})
~~~

Lệnh có thể ghi document sai schema **chỉ khi** tài khoản và cấu hình cho phép bỏ qua validation. Không nên chạy với dữ liệu thật nếu không có kế hoạch migration rõ ràng. Người dùng ứng dụng thông thường nên được cấp quyền tối thiểu và không dùng bypass như cách xử lý lỗi ghi.

### 18.2. Những tình huống lỗi điển hình

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Ghi lỗi Document failed validation | Document không thỏa một hoặc nhiều điều kiện | Xem validator và BSON type thực tế của field |
| Trường total nhìn giống số nhưng bị từ chối | Đang là String/Double thay vì Decimal128 | Tạo Decimal128 đúng ở ứng dụng/driver |
| createdAt có ISO-8601 nhưng lỗi kiểu | Giá trị được lưu dưới dạng String | Chuyển sang BSON Date khi tạo document |
| Document thiếu name vẫn được ghi | Chỉ có properties, không có required | Thêm name vào required |
| Không thể insert khi additionalProperties: false | _id hoặc trường mới chưa được khai báo | Khai báo _id và trường được phép, hoặc điều chỉnh chính sách |
| Có thể ghi dữ liệu sai dù đã tạo schema | validationAction là warn, validationLevel là off hoặc có bypass | Kiểm tra metadata và quyền ghi |
| Lệnh createCollection báo đã tồn tại | Collection đã có | Dùng collMod để cập nhật validator trong trường hợp được hỗ trợ |
| Có document sai schema sau khi bật strict | Dữ liệu cũ không tự được sửa hoặc xóa | Kiểm kê và migration dữ liệu cũ |
| Chỉ một số update bị lỗi sau khi bật schema | Update làm document vi phạm required/type hoặc dữ liệu cũ sai schema | Kiểm tra dữ liệu trước/sau cập nhật, cân nhắc lộ trình migration |
| Hai sản phẩm trùng sku vẫn lưu được | $jsonSchema không kiểm tra duy nhất giữa các document | Tạo unique index |
| Validation sai sau khi thay đổi Java model | Codec/mapping gửi loại BSON khác schema | Kiểm tra ObjectId, Date, int/long/double/decimal và schema đang lưu |

### 18.3. Quan sát validator và kiểm tra BSON type

Xem metadata:

~~~javascript
db.getCollectionInfos({ name: "products" })
~~~

Xem kiểu BSON thực tế của một số trường bằng aggregation:

~~~javascript
db.products.aggregate([
  {
    $project: {
      sku: 1,
      priceType: { $type: "$price" },
      stockType: { $type: "$stock" },
      createdAtType: { $type: "$createdAt" }
    }
  },
  { $limit: 10 }
])
~~~

Kết quả có thể hiển thị các tên kiểu như **decimal**, **int**, **date**. Cách này hữu ích khi dữ liệu đến từ nhiều nguồn và bạn không chắc driver đã mã hóa giá trị thành loại BSON nào.

### 18.4. Tránh thay đổi schema đột ngột

Việc bật strict + error có thể khiến ứng dụng cũ ghi thất bại, ngay cả khi API phía ngoài chưa đổi. Khi cần đổi contract dữ liệu, nên thực hiện bước chuyển giao gồm kiểm kê, cập nhật tất cả nguồn ghi, migration dữ liệu và theo dõi lỗi. Với hệ thống nhiều service, thời điểm cập nhật code và thời điểm cập nhật schema cần được điều phối.

## 19. Bài tập thực hành

### Bài 1. Tạo collection học viên

Tạo collection **students** với các yêu cầu:

- **studentCode:** bắt buộc, String, từ 3 đến 15 ký tự.
- **fullName:** bắt buộc, String, không rỗng.
- **age:** tùy chọn, Int32, trong khoảng 16 đến 100.
- **enrolledAt:** bắt buộc, BSON Date.
- **skills:** tùy chọn, Array tối đa 10 phần tử, mỗi phần tử là String.
- Cho phép _id mặc định; không cho phép trường khác.
- Sử dụng strict và error.

**Đáp án tham khảo:**

~~~javascript
db.createCollection("students", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentCode", "fullName", "enrolledAt"],
      additionalProperties: false,
      properties: {
        _id: { bsonType: "objectId" },
        studentCode: {
          bsonType: "string",
          minLength: 3,
          maxLength: 15
        },
        fullName: {
          bsonType: "string",
          minLength: 1
        },
        age: {
          bsonType: "int",
          minimum: 16,
          maximum: 100
        },
        enrolledAt: {
          bsonType: "date"
        },
        skills: {
          bsonType: "array",
          maxItems: 10,
          items: { bsonType: "string" }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Tự kiểm thử một document hợp lệ:

~~~javascript
db.students.insertOne({
  studentCode: "ST-001",
  fullName: "Lan",
  age: NumberInt(21),
  enrolledAt: new Date(),
  skills: ["Java", "MongoDB"]
})
~~~

Rồi thử thay **age** bằng chuỗi "21", thay **enrolledAt** bằng chuỗi ISO hoặc bỏ **fullName** để quan sát lỗi.

### Bài 2. Phân biệt required và nullable

Một trường **phone** được khai báo:

~~~javascript
phone: {
  bsonType: ["string", "null"]
}
~~~

Hãy giải thích sự khác biệt của các trường hợp:

1. Document không có phone.
2. phone là null.
3. phone là "0900000000".
4. phone là NumberLong("900000000").

**Gợi ý:** ba trường hợp đầu hợp lệ nếu phone không nằm trong required; trường hợp thứ tư sai kiểu. Khi thêm phone vào required, trường hợp đầu trở thành không hợp lệ, nhưng phone: null vẫn hợp lệ.

### Bài 3. Validator và unique index

Hệ thống yêu cầu email:

- Có kiểu String và pattern đơn giản.
- Không được trùng giữa hai user khác nhau.

Hãy xác định phần nào dùng $jsonSchema và phần nào cần unique index. Giải thích vì sao chỉ dùng enum hoặc required không thể bảo đảm email duy nhất trong collection.

### Bài 4. Triển khai schema cho dữ liệu cũ

Collection **employees** đã có nhiều record với salary lúc là String, lúc là Double. Schema mới yêu cầu Decimal128 không âm.

Hãy đề xuất lộ trình:

1. Kiểm kê từng kiểu salary bằng $type.
2. Chốt đơn vị tiền và chính sách chuyển đổi.
3. Cập nhật code ghi để dùng Decimal128.
4. Chuyển dữ liệu cũ có thể chuyển đổi an toàn, xử lý ngoại lệ.
5. Thêm validator và theo dõi cảnh báo.
6. Bật strict + error sau khi dữ liệu và client đã phù hợp.

Giải thích vì sao chỉ đổi validationAction sang error ngay từ đầu có thể gây lỗi ghi cho các ứng dụng còn dùng kiểu cũ.

### Bài 5. Tìm document vi phạm schema

Dùng lệnh:

~~~javascript
db.students.find({
  $nor: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["studentCode", "fullName", "enrolledAt"],
        properties: {
          studentCode: { bsonType: "string" },
          fullName: { bsonType: "string" },
          enrolledAt: { bsonType: "date" }
        }
      }
    }
  ]
})
~~~

Hãy giải thích vì sao truy vấn này tìm document không thỏa **schema nhỏ được viết trong truy vấn**, chứ không tự động sao chép mọi quy tắc từ validator hiện có. Muốn rà soát đầy đủ, dùng cùng bộ quy tắc schema đích để tránh bỏ sót điều kiện.

## 20. Những nguyên tắc cần ghi nhớ

1. **$jsonSchema** mô tả cấu trúc document và điều kiện về giá trị; **bsonType** mô tả loại BSON thực sự được lưu.
2. **required** chỉ kiểm tra sự hiện diện của field; muốn field có đúng kiểu và giá trị, khai báo thêm trong **properties**.
3. Với object và array lồng nhau, đặt quy tắc tại đúng cấp; **additionalProperties: false** cần tính cả trường _id của MongoDB.
4. **validationLevel** quyết định phạm vi kiểm tra; **validationAction** quyết định cảnh báo hay từ chối khi kiểm tra thất bại.
5. Thêm hoặc sửa validator **không tự chuyển đổi dữ liệu cũ**. Khi thay đổi schema cần kế hoạch migration, cập nhật nguồn ghi và xác minh dữ liệu.
6. Schema validation kiểm tra từng document, còn tính duy nhất giữa các document cần **unique index** và những ràng buộc nghiệp vụ khác phải được thiết kế riêng.

Khai báo validator chặt chẽ giúp MongoDB trở thành điểm kiểm soát chung cho nhiều ứng dụng và script cùng ghi dữ liệu. Khi hiểu rõ **$jsonSchema**, **bsonType**, các quy tắc lồng nhau và tùy chọn validation, bạn có thể tận dụng sự linh hoạt của document database mà vẫn duy trì hợp đồng dữ liệu nhất quán.
