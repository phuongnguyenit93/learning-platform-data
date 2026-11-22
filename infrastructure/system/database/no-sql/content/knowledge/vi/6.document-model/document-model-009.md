# Schema validation và quy tắc giữa các trường

Một lợi thế của cơ sở dữ liệu **document NoSQL** là tài liệu có thể mang cấu trúc linh hoạt: các sản phẩm khác loại có những thuộc tính khác nhau; một hồ sơ người dùng có địa chỉ lồng nhau; một đơn hàng chứa danh sách mặt hàng ngay trong tài liệu. Tuy nhiên, **linh hoạt về cấu trúc không có nghĩa ứng dụng được phép lưu mọi dữ liệu tùy ý**. Nếu không có quy tắc, cùng một trường `price` có thể khi là số, khi là chuỗi; `status = ACTIVE` nhưng `publishedAt` vắng mặt; hoặc `startsAt` xảy ra sau `endsAt`.

**Schema validation** giúp kiểm tra hình dạng và tính hợp lệ của tài liệu. **Quy tắc giữa các trường (cross-field constraints)** kiểm tra mối quan hệ giữa nhiều giá trị của cùng tài liệu. Hai lớp này bổ sung cho nhau: một `startsAt` có kiểu ngày và một `endsAt` có kiểu ngày chưa đủ để khẳng định `startsAt < endsAt`.

Trong chủ đề **Mô hình tài liệu**, mục tiêu là xác định các bất biến dữ liệu, đặt chúng ở đúng nơi có thể thực thi, hiểu giới hạn của validator trong NoSQL, rồi đưa schema vào vận hành mà vẫn cho phép ứng dụng tiến hóa theo thời gian.

> Ví dụ xuyên suốt: ứng dụng thương mại điện tử lưu chương trình khuyến mãi dạng tài liệu trong MongoDB. Mỗi khuyến mãi có mã, kiểu giảm giá, giá trị, thời gian bắt đầu/kết thúc, trạng thái và thời điểm công bố. Ví dụ MongoDB là cách minh họa cụ thể; các document database khác có cơ chế hoặc mức độ hỗ trợ khác nhau.

## 1. Document có cấu trúc linh hoạt vẫn cần hợp đồng dữ liệu

Xét một chương trình khuyến mãi hợp lệ:

~~~json
{
  "code": "NOVEMBER10",
  "kind": "PERCENT",
  "amount": 10,
  "startsAt": "2026-11-14T00:00:00Z",
  "endsAt": "2026-11-21T00:00:00Z",
  "status": "ACTIVE",
  "publishedAt": "2026-11-13T10:00:00Z"
}
~~~

Ví dụ trên là **JSON trao đổi qua API**: thời điểm biểu diễn bằng chuỗi ISO 8601 và `amount` là JSON number. Khi lưu trong MongoDB, ứng dụng có thể chuyển các giá trị ấy thành **BSON Date** và **Decimal128**. **JSON trong request, kiểu trong object Java và kiểu BSON trong database là ba lớp cần phân biệt**; trông giống nhau khi in ra không có nghĩa có cùng kiểu hoặc độ chính xác.

Các tài liệu sau đều có vấn đề, dù về cú pháp chúng vẫn có thể là JSON hợp lệ:

~~~json
{
  "code": "NOVEMBER10",
  "kind": "PERCENT",
  "amount": "10%",
  "startsAt": "2026-11-21T00:00:00Z",
  "endsAt": "2026-11-14T00:00:00Z",
  "status": "ACTIVE"
}
~~~

- `amount` là chuỗi `"10%"` thay vì số theo hợp đồng.
- `startsAt` xảy ra sau `endsAt`.
- `status` là `ACTIVE` nhưng không có `publishedAt`.

Một schema chỉ quy định “`amount` là số, `startsAt` và `endsAt` là ngày” vẫn **không bắt được hai lỗi quan hệ sau cùng**. Ngược lại, quy tắc thời gian cũng không thay thế kiểm tra kiểu: so sánh hai chuỗi thời gian không chuẩn hóa có thể sinh kết quả sai.

### 1.1. Những loại quy tắc khác nhau

| Loại quy tắc | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Presence** | Trường nào bắt buộc xuất hiện? | Phải có `code`, `kind`, `startsAt`, `endsAt` |
| **Type** | Giá trị thuộc kiểu gì? | `startsAt` là BSON Date, `amount` là Decimal128 |
| **Range/format** | Một giá trị đơn lẻ có hợp lệ không? | `amount >= 0`; `code` không rỗng |
| **Enum** | Giá trị có thuộc tập cho phép? | `kind` là `PERCENT` hoặc `FIXED` |
| **Shape/nested** | Object/mảng con được tổ chức thế nào? | Mỗi phần tử `items` có `sku` và `quantity` |
| **Cross-field** | Các trường trong một tài liệu có phù hợp nhau? | `startsAt < endsAt`; phần trăm giảm không quá 100 |
| **State transition** | Sự thay đổi từ trạng thái cũ sang mới có hợp lệ? | Không chuyển trực tiếp `ARCHIVED -> ACTIVE` nếu nghiệp vụ cấm |
| **Cross-document** | Quy tắc liên quan nhiều tài liệu có giữ đúng không? | Mã khuyến mãi duy nhất; không cấp hai lần một suất còn lại |

Các nhóm sau cùng đòi công cụ khác nhau. **Không phải mọi bất biến nghiệp vụ đều có thể diễn đạt bằng schema của một tài liệu.**

## 2. Phân biệt schema validation với xử lý nghiệp vụ

Schema thường trả lời **“Bản ghi này có được phép tồn tại trong kho dữ liệu hay không?”**. Một thao tác nghiệp vụ còn phải trả lời:

- Người gọi có quyền công bố chương trình khuyến mãi này không?
- Có được sửa `amount` khi chương trình đã bắt đầu không?
- Ngân sách khuyến mãi còn đủ để duyệt thêm một đơn hàng không?
- Mã `NOVEMBER10` đã được dùng ở tài liệu khác chưa?
- Một cập nhật cũ có đang ghi đè thay đổi mới hơn không?

Các câu hỏi này có thể cần xác thực/phân quyền, đọc trạng thái cũ, kiểm tra nhiều tài liệu, cập nhật nguyên tử hoặc giao dịch. **Schema là một hàng rào đúng đắn của dữ liệu**, nhưng không phải bộ máy nghiệp vụ đầy đủ.

Đừng thiết kế validator khổng lồ để thay cho domain model. Ngược lại, nếu chỉ kiểm tra ở controller, một script import, một job nền hoặc một service khác có thể ghi thẳng vào database và bỏ qua những điều kiện mà controller từng kiểm tra.

## 3. Các tầng thực thi validation

Một ứng dụng thường có nhiều lớp bảo vệ:

~~~mermaid
flowchart TD
    U["Client / API request"] --> A["API validation\nKiểu đầu vào, trường bắt buộc, thông báo lỗi"]
    A --> B["Domain validation\nBất biến nghiệp vụ, chuyển trạng thái, quyền"]
    B --> D["Database write\nAtomic update / transaction"]
    D --> V["Document schema validator\nHình dạng và quy tắc trong tài liệu"]
    V --> S[("Document store")]
    I["Batch import / worker / service khác"] --> D
~~~

Sơ đồ là phân chia trách nhiệm; trong thực tế database đánh giá validator như một phần đường thực thi ghi, không phải một bước ứng dụng có thể tự gọi rồi chắc chắn database sẽ chấp nhận.

| Tầng | Nên kiểm tra gì? | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Client/UI** | Bắt buộc nhập, định dạng, gợi ý tương tác | Báo lỗi sớm, trải nghiệm tốt | Người gọi có thể bỏ qua; không bảo vệ dữ liệu |
| **API/DTO** | Parse JSON, kiểu, độ dài, input contract | Lỗi gần đầu vào, dễ trả mã và thông báo rõ | Worker/import có thể không qua API |
| **Domain/application** | Quan hệ trường, trạng thái cũ/mới, quyền, điều kiện nghiệp vụ | Giữ quy tắc giàu ngữ cảnh | Có thể có nhiều đường ghi; phải thống nhất |
| **Database document validator** | Kiểu BSON, required, enum, khoảng giá trị, một số biểu thức kiểm tra tài liệu | Hàng rào chung cho các đường ghi bị áp dụng validation | Không thay cho uniqueness, authorization hoặc giao dịch liên tài liệu |
| **Index/atomic write/transaction** | Duy nhất, tranh chấp, điều kiện phụ thuộc trạng thái hiện có | Bảo vệ bất biến dưới ghi đồng thời | Cần thiết kế khóa, phạm vi giao dịch và xử lý xung đột |
| **Migration và monitoring** | Dữ liệu lịch sử, sai lệch sau thay đổi schema | Phát hiện nợ dữ liệu và tiến hóa an toàn | Không tự làm bản ghi hợp lệ ngay khi quy tắc mới được ban hành |

Quy tắc quan trọng có thể được **diễn đạt ở hơn một lớp**, nhưng phải có một hợp đồng nghiệp vụ thống nhất để tránh một lớp chấp nhận và lớp khác từ chối cùng một bản ghi.

## 4. Required, optional, missing và null khác nhau

Trong mô hình document, thiếu trường và trường chứa `null` là hai trạng thái khác nhau:

~~~json
{ "name": "Đèn bàn" }
~~~

~~~json
{ "name": "Đèn bàn", "description": null }
~~~

~~~json
{ "name": "Đèn bàn", "description": "" }
~~~

Trường `description` trong ba trường hợp lần lượt **không tồn tại**, **tồn tại với giá trị null**, **tồn tại với chuỗi rỗng**. Tùy nghiệp vụ, chúng có thể mang ý nghĩa khác nhau:

- **Missing:** dữ liệu cũ chưa có trường, chưa nhập, hoặc không áp dụng.
- **Null:** ứng dụng chủ động ghi nhận “chưa có giá trị/không xác định”.
- **Empty:** người dùng truyền một chuỗi đã xác định nhưng không có ký tự.

Với MongoDB `$jsonSchema`, từ khóa `required` kiểm tra trường **có mặt**, không tự bảo đảm giá trị khác `null`. Muốn bắt buộc là chuỗi, có thể yêu cầu `bsonType: "string"`; nếu cho phép null, khai báo tập kiểu có `"null"`.

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string", minLength: 1 },
      description: { bsonType: ["string", "null"] }
    }
  }
}
~~~

Ở đây `description` **không bắt buộc**. Nếu có, nó chỉ được là chuỗi hoặc null. `name` bắt buộc, phải là chuỗi và có tối thiểu một ký tự; nếu cần cấm chuỗi chỉ chứa khoảng trắng thì phải thêm quy tắc phù hợp, chẳng hạn chuẩn hóa `trim` ở đầu vào hoặc dùng pattern được hỗ trợ.

**Một số điều cần cẩn trọng:**

- Không nên tự động chuyển mọi `null` thành trường bị thiếu; điều đó có thể thay đổi ý nghĩa cập nhật dữ liệu.
- Khi API hỗ trợ PATCH, “không gửi field” thường có nghĩa **không thay đổi**, còn “gửi null” có thể là **xóa giá trị**. Đây là hợp đồng API, cần được định nghĩa tường minh.
- Quy tắc `required` ở nested object phải đặt tại đúng cấp; `required` của object gốc không buộc những field con xuất hiện nếu không khai báo.

## 5. Schema cho tài liệu lồng nhau và mảng

Document database cho phép gom dữ liệu liên quan vào một tài liệu:

~~~json
{
  "orderId": "ORD-91",
  "customer": {
    "customerId": "U-8",
    "displayName": "Lan"
  },
  "items": [
    { "sku": "BOOK-1", "quantity": 2, "unitPriceMinor": 79000 },
    { "sku": "PEN-3", "quantity": 1, "unitPriceMinor": 12000 }
  ]
}
~~~

Schema có thể kiểm tra:

- `customer` phải là object và có `customerId` dạng chuỗi.
- `items` phải là mảng, chứa ít nhất một phần tử.
- Mỗi phần tử `items` phải là object có `sku`, `quantity`, `unitPriceMinor`.
- `quantity` phải là số nguyên dương.
- `unitPriceMinor` phải là số nguyên không âm nếu hệ thống lưu tiền theo đơn vị nhỏ nhất.

Ví dụ bộ quy tắc MongoDB `$jsonSchema`:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["orderId", "customer", "items"],
    properties: {
      orderId: { bsonType: "string", minLength: 1 },
      customer: {
        bsonType: "object",
        required: ["customerId"],
        properties: {
          customerId: { bsonType: "string", minLength: 1 },
          displayName: { bsonType: "string" }
        }
      },
      items: {
        bsonType: "array",
        minItems: 1,
        items: {
          bsonType: "object",
          required: ["sku", "quantity", "unitPriceMinor"],
          properties: {
            sku: { bsonType: "string", minLength: 1 },
            quantity: { bsonType: "int", minimum: 1 },
            unitPriceMinor: { bsonType: "long", minimum: 0 }
          }
        }
      }
    }
  }
}
~~~

**Lưu ý về kiểu số BSON:** một giá trị JSON `2` khi đi qua driver có thể trở thành BSON Int32, Int64 hoặc một dạng số khác tùy mapping. Quy tắc `bsonType: "int"` và `bsonType: "long"` là hai yêu cầu khác nhau. Cần kiểm tra dữ liệu mà driver thực sự ghi; ví dụ chỉ minh họa một hợp đồng đã thống nhất giữa các bên ghi.

Những quy tắc như “tổng tiền đơn hàng bằng tổng các dòng” hoặc “`quantity` phải phù hợp `reservedQuantity`” lại là **quan hệ giữa trường**, cần một biểu thức kiểm tra thêm, hoặc logic miền nghiệp vụ giữ bất biến khi cập nhật.

### 5.1. Có nên cấm mọi field ngoài schema?

Một số JSON Schema validator có quy tắc `additionalProperties: false` để từ chối trường chưa khai báo. Ưu điểm là phát hiện lỗi gõ tên như `quanitty` thay vì `quantity`. Nhược điểm là gây khó khăn khi mở rộng schema và rollout nhiều phiên bản.

Với MongoDB, nếu cấm field ngoài danh sách, cần tính đến `_id` và mọi field kỹ thuật được driver/hệ thống thêm vào. Nếu không định nghĩa `_id` trong `properties`, validator có thể từ chối một tài liệu vì trường này được thêm tự động. Không nên bật đóng schema cứng một cách máy móc.

Một lựa chọn khác là **kiểm tra chặt các field nghiệp vụ quan trọng, cho phép field mở rộng có kiểm soát**; đồng thời theo dõi dữ liệu bất thường. Quyết định phụ thuộc yêu cầu tương thích và khả năng quản lý nhiều bên ghi.

## 6. Quy tắc giữa các trường: những dạng thường gặp

Schema field-by-field chỉ xem từng giá trị độc lập; cross-field constraints diễn đạt quan hệ trong một bản ghi.

### 6.1. Khoảng thời gian hợp lệ

Giả sử khuyến mãi có:

~~~text
startsAt = 2026-11-14T08:00:00Z
endsAt   = 2026-11-14T07:00:00Z
~~~

Cả hai trường đều là thời điểm hợp lệ, nhưng khoảng thời gian không hợp lệ nếu yêu cầu `startsAt < endsAt`.

**Phải chọn quy ước biên:** khoảng `[startsAt, endsAt)` (bao gồm lúc bắt đầu, không bao gồm lúc kết thúc) thường giúp nối tiếp các khoảng không bị trùng ở biên. Nếu nghiệp vụ cho phép sự kiện có thời lượng bằng 0, quy tắc có thể là `<=`; nếu bắt buộc có thời lượng dương, dùng `<`. Đây là quyết định của nghiệp vụ.

### 6.2. Giá trị phụ thuộc loại

~~~text
kind = PERCENT  => amount nằm trong khoảng (0, 100]
kind = FIXED    => amount > 0, đơn vị tiền tệ phải được xác định
~~~

Giá trị `amount = 120` hợp lệ về kiểu số nhưng không hợp lệ nếu `kind = PERCENT`. Nếu `kind = FIXED`, giới hạn trên có thể phụ thuộc vào giá sản phẩm hoặc điều kiện ngân sách ngoài tài liệu, nên không phải mọi kiểm tra đều nằm trong một validator.

**Tiền tệ và tỷ lệ:** tránh tính tiền nghiệp vụ quan trọng bằng số thực nhị phân một cách tùy tiện. Có thể dùng `Decimal128` hoặc số nguyên theo đơn vị nhỏ nhất, kèm `currency` và quy tắc làm tròn rõ ràng. Hợp đồng lưu trữ cần nhất quán với logic tính toán.

### 6.3. Field bắt buộc theo trạng thái

~~~text
status = DRAFT   => publishedAt có thể thiếu
status = ACTIVE  => publishedAt bắt buộc và phải là ngày
status = ARCHIVED => archivedAt có thể là trường bắt buộc
~~~

Tập field bắt buộc thay đổi theo **trạng thái hiện tại của tài liệu**. Schema thuần `required: ["publishedAt"]` sẽ sai vì buộc bản nháp cũng phải có ngày công bố. Cần quy tắc điều kiện giữa các trường.

Điều này vẫn khác với **chuyển trạng thái**. Validator thấy `status = ACTIVE` và `publishedAt` hiện có chỉ chứng minh **trạng thái cuối** hợp lệ, không biết tài liệu trước đó đã là `ARCHIVED` hay `DRAFT`. Nếu cấm chuyển `ARCHIVED -> ACTIVE`, phải kiểm tra trạng thái cũ bằng domain logic và thao tác cập nhật có điều kiện.

### 6.4. Giá trị tổng hợp và danh sách

Đối với một đơn hàng:

~~~text
subtotal = SUM(items.quantity * items.unitPriceMinor)
total    = subtotal - discountMinor + shippingMinor
~~~

Đây là bất biến giữa các trường và các phần tử mảng trong cùng tài liệu. Có thể tính ở domain layer khi tạo/sửa đơn và ghi lại giá trị cuối; tùy khả năng engine, một số biểu thức kiểm tra có thể chạy tại database. Nhưng nếu `discountMinor` dựa vào chiến dịch bên ngoài hoặc `shippingMinor` do dịch vụ vận chuyển quyết định, logic nghiệp vụ phải xử lý nguồn có thẩm quyền và thời điểm chốt giá.

Với dữ liệu tài chính, nên cân nhắc **lưu snapshot của giá đã chốt** và phiên bản quy tắc tính, thay vì phụ thuộc vào giá sản phẩm hiện tại khi đọc lại đơn cũ.

## 7. Thực hành MongoDB: `$jsonSchema` và biểu thức kiểm tra

MongoDB cho phép gắn **validator** với collection. `$jsonSchema` diễn đạt một tập quy tắc cho cấu trúc BSON; các **query expression** được hỗ trợ có thể kiểm tra quan hệ giữa những giá trị trong tài liệu.

Ví dụ dưới đây minh họa cùng lúc:

- Field `code`, `kind`, `amount`, `startsAt`, `endsAt`, `status` bắt buộc.
- `amount` lưu dưới dạng Decimal128, không âm.
- `startsAt` phải trước `endsAt`.
- Nếu `kind = PERCENT`, `amount` tối đa 100.
- Nếu `status = ACTIVE`, `publishedAt` phải hiện diện dưới dạng BSON Date.

~~~javascript
db.createCollection("promotions", {
  validator: {
    $and: [
      {
        $jsonSchema: {
          bsonType: "object",
          required: [
            "code", "kind", "amount",
            "startsAt", "endsAt", "status"
          ],
          properties: {
            code: {
              bsonType: "string",
              minLength: 1
            },
            kind: {
              enum: ["PERCENT", "FIXED"]
            },
            amount: {
              bsonType: "decimal",
              minimum: 0
            },
            startsAt: {
              bsonType: "date"
            },
            endsAt: {
              bsonType: "date"
            },
            status: {
              enum: ["DRAFT", "ACTIVE", "ARCHIVED"]
            },
            publishedAt: {
              bsonType: "date"
            }
          }
        }
      },
      {
        $expr: {
          $lt: ["$startsAt", "$endsAt"]
        }
      },
      {
        $expr: {
          $or: [
            { $ne: ["$kind", "PERCENT"] },
            { $lte: ["$amount", NumberDecimal("100")] }
          ]
        }
      },
      {
        $expr: {
          $or: [
            { $ne: ["$status", "ACTIVE"] },
            { $eq: [{ $type: "$publishedAt" }, "date"] }
          ]
        }
      }
    ]
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

**Cần hiểu ý nghĩa các thành phần:**

- `$jsonSchema` xác định hình dạng và kiểu BSON; bộ từ khóa của MongoDB **không phải toàn bộ mọi phiên bản JSON Schema**. Không sao chép một file JSON Schema bất kỳ rồi kỳ vọng tất cả từ khóa như `if/then/else` đều hoạt động giống một thư viện JSON Schema ở ứng dụng.
- `$expr` cho phép đánh giá các aggregation expression phù hợp để so sánh trường trong **chính tài liệu đang được xác thực**. Không coi nó là cách join dữ liệu của tài liệu khác hay thay cho transaction.
- `validationLevel: "strict"` áp dụng kiểm tra cho các thao tác ghi nằm trong phạm vi validation; `validationAction: "error"` từ chối thay đổi không đạt.
- Các toán tử/biểu thức có thể có giới hạn trong validator; khi triển khai thật phải xác nhận phiên bản MongoDB, driver và hình dạng dữ liệu được hỗ trợ.

Điều kiện `amount >= 0` là lựa chọn minh họa. Nếu mọi chương trình giảm giá bắt buộc có giá trị dương, cần sửa quy tắc thành `amount > 0` ở tầng phù hợp. Một `PERCENT` bằng 0 có thể là chương trình vô nghĩa dù không gây lỗi tính toán; tính hợp lệ phải phản ánh đúng hợp đồng nghiệp vụ.

### 7.1. Ghi một tài liệu hợp lệ

MongoDB shell có thể lưu Date và Decimal128 dưới kiểu BSON tương ứng:

~~~javascript
db.promotions.insertOne({
  code: "NOVEMBER10",
  kind: "PERCENT",
  amount: NumberDecimal("10"),
  startsAt: ISODate("2026-11-14T00:00:00Z"),
  endsAt: ISODate("2026-11-21T00:00:00Z"),
  status: "ACTIVE",
  publishedAt: ISODate("2026-11-13T10:00:00Z")
});
~~~

Nếu ứng dụng gửi `amount: "10"` dưới dạng chuỗi, nó sẽ không đáp ứng `bsonType: "decimal"`. Nếu gửi `amount: 10` dưới kiểu số khác Decimal128, cần xem driver serialize ra BSON nào. **Schema ở database không tự thực hiện chuyển kiểu giúp ứng dụng.**

### 7.2. Ghi tài liệu không hợp lệ

~~~javascript
db.promotions.insertOne({
  code: "BAD-DATE",
  kind: "PERCENT",
  amount: NumberDecimal("120"),
  startsAt: ISODate("2026-11-22T00:00:00Z"),
  endsAt: ISODate("2026-11-21T00:00:00Z"),
  status: "ACTIVE"
});
~~~

Tài liệu này vi phạm **ba loại quy tắc**: phần trăm trên 100, thời gian bắt đầu sau kết thúc và thiếu `publishedAt` khi `status = ACTIVE`. Khi validation đang được áp dụng ở chế độ `error`, thao tác ghi bị từ chối.

Database có thể trả thông tin lỗi kèm chi tiết quy tắc; ứng dụng nên ánh xạ lỗi thành thông báo có ý nghĩa và tránh trả nguyên mọi thông tin nội bộ nhạy cảm cho client.

### 7.3. `validationLevel` và `validationAction`

Hai nhóm cấu hình có trách nhiệm khác nhau:

| Cấu hình | Ý nghĩa chính |
| --- | --- |
| `validationLevel: "strict"` | Kiểm tra insert và update theo validation đã cấu hình |
| `validationLevel: "moderate"` | Kiểm tra insert và update của tài liệu hiện tại đã hợp lệ; có ngoại lệ cho các tài liệu tồn tại từ trước đang không đạt validation |
| `validationAction: "error"` | Từ chối thay đổi không hợp lệ khi validation áp dụng |
| `validationAction: "warn"` | Cho phép thay đổi nhưng ghi cảnh báo về vi phạm vào log theo hành vi sản phẩm |

Điều này hữu ích khi thay đổi schema trên collection đã có dữ liệu cũ. Tuy nhiên:

1. Chuyển sang `warn` **không làm dữ liệu mới hợp lệ**; nó chỉ giúp quan sát vi phạm mà chưa chặn ghi.
2. `moderate` **không sửa dữ liệu cũ** và không tự bảo đảm mọi tài liệu sau một thời gian đều đạt schema.
3. Một số thao tác đặc quyền có thể sử dụng khả năng bỏ qua document validation nếu được cấp quyền. Cần quản lý quyền ghi và quy trình import/migration.
4. Tạo hoặc sửa validator **không tự backfill hay ép toàn bộ tài liệu đang lưu phải thỏa mãn ngay**. Cần công việc kiểm tra dữ liệu hiện có riêng.

Validator có thể được thay bằng lệnh quản trị như `collMod`; nên quản lý nó dưới dạng cấu hình có phiên bản trong quy trình triển khai, tránh chỉnh tay không có lịch sử.

## 8. Kiểm tra ở ứng dụng: validation của object hoàn chỉnh

Validator cơ sở dữ liệu hữu ích, nhưng ứng dụng vẫn cần phản hồi lỗi sớm và diễn đạt nghiệp vụ dễ hiểu.

Ví dụ Java 21 cho một object đầu vào; đây là logic kiểm tra miền dữ liệu, có thể được gọi sau bước parse/validate DTO:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

enum PromotionKind { PERCENT, FIXED }
enum PromotionStatus { DRAFT, ACTIVE, ARCHIVED }

public record PromotionInput(
        String code,
        PromotionKind kind,
        BigDecimal amount,
        Instant startsAt,
        Instant endsAt,
        PromotionStatus status,
        Instant publishedAt
) {
    public void validate() {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code must not be blank");
        }
        Objects.requireNonNull(kind, "kind is required");
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(startsAt, "startsAt is required");
        Objects.requireNonNull(endsAt, "endsAt is required");
        Objects.requireNonNull(status, "status is required");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must be >= 0");
        }
        if (!startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException("startsAt must precede endsAt");
        }
        if (kind == PromotionKind.PERCENT
                && amount.compareTo(new BigDecimal("100")) > 0) {
            throw new IllegalArgumentException("percentage must be <= 100");
        }
        if (status == PromotionStatus.ACTIVE && publishedAt == null) {
            throw new IllegalArgumentException("active promotion needs publishedAt");
        }
    }
}
~~~

Ở ứng dụng Spring Boot, có thể kết hợp **Jakarta Bean Validation** (ví dụ `@NotNull`, `@NotBlank`, `@Positive` và custom class-level constraint) với một domain method như trên. Class-level validation thích hợp khi lỗi phụ thuộc nhiều trường; domain method hữu ích khi thao tác có ngữ cảnh như người dùng, trạng thái trước đó hoặc quyền.

**Tuy vậy, kiểm tra rồi ghi vẫn có thể gặp race condition.** Hai request cùng đọc trạng thái hợp lệ, đều kiểm tra thành công, sau đó cùng thay đổi dữ liệu. Cần cơ chế atomic update, version/optimistic concurrency, unique index hoặc transaction tương ứng với ràng buộc cần bảo vệ.

### 8.1. Cập nhật một phần (PATCH) cần một bước hợp nhất

Giả sử khuyến mãi đang lưu:

~~~json
{
  "startsAt": "2026-11-14T00:00:00Z",
  "endsAt": "2026-11-21T00:00:00Z"
}
~~~

Client gửi:

~~~json
{
  "startsAt": "2026-11-22T00:00:00Z"
}
~~~

Đầu vào PATCH không có `endsAt` nên không thể chỉ validate hai trường của **payload PATCH** rồi kết luận dữ liệu cuối hợp lệ. Cần kiểm tra **tài liệu sau khi áp dụng thay đổi**. Với MongoDB, update được validation áp dụng sẽ bị kiểm tra theo tài liệu sau cập nhật ở phạm vi được áp dụng; vẫn nên kiểm tra ở ứng dụng để trả lỗi nghiệp vụ rõ ràng.

Một workflow phù hợp:

~~~text
Đọc trạng thái hiện tại kèm version
        ↓
Kiểm tra quyền và thay đổi được phép
        ↓
Áp dụng PATCH lên mô hình hoàn chỉnh
        ↓
Validate các quy tắc giữa trường
        ↓
Ghi có điều kiện theo version + database validator
        ↓
Nếu xung đột: trả 409 hoặc xử lý retry theo hợp đồng
~~~

Nếu một request đổi `status` thành `ACTIVE`, cần bảo đảm `publishedAt` được set trong cùng thao tác ghi hợp lệ, tránh tài liệu tạm có trạng thái ACTIVE nhưng thiếu thời điểm công bố.

## 9. Quy tắc trên một tài liệu khác quy tắc giữa nhiều tài liệu

Một giới hạn quan trọng của document validator là nó nhìn thấy **tài liệu được kiểm tra**, không tự biết trạng thái toàn bộ collection hoặc của các service khác.

### 9.1. Duy nhất: dùng index phù hợp

Nếu `code` chương trình phải duy nhất trong một tenant, `$jsonSchema` không đủ:

~~~javascript
db.promotions.createIndex(
  { tenantId: 1, code: 1 },
  { unique: true }
);
~~~

Một unique index giúp database thực thi ràng buộc duy nhất dưới ghi đồng thời theo hợp đồng index. Cần làm rõ cách xử lý giá trị null/missing, collation và phạm vi tenant; nếu chỉ cần duy nhất với tài liệu đang ACTIVE thì có thể cần thiết kế index có điều kiện được hỗ trợ và kiểm tra đúng biểu thức.

Mẫu “query xem code đã tồn tại chưa, nếu chưa thì insert” **không chống được race** khi hai tiến trình cùng query trước lúc một trong hai insert. Unique index hoặc một thao tác có điều kiện nguyên tử mới là hàng rào đáng tin hơn.

### 9.2. Bất biến số lượng: dùng ghi có điều kiện

Một chương trình có `remainingUses = 1`. Hai request đồng thời đều muốn trừ một lượt.

Đừng làm:

~~~text
Request A đọc remainingUses = 1
Request B đọc remainingUses = 1
Cả hai cùng kiểm tra > 0
Cả hai cùng đặt remainingUses = 0
=> Có thể chấp nhận hai lượt dùng dù quota chỉ một
~~~

Với ràng buộc trong **một tài liệu**, dùng atomic conditional update:

~~~javascript
const result = db.promotions.updateOne(
  { _id: "PROMO-1", remainingUses: { $gt: 0 } },
  { $inc: { remainingUses: -1 } }
);

if (result.matchedCount === 0) {
  // Không còn lượt dùng hoặc khuyến mãi không tồn tại.
}
~~~

Điều kiện và thao tác trừ cần diễn ra nguyên tử trong database. Nếu đồng thời còn phải tạo một bản ghi `redemption` riêng và bảo đảm “mỗi user chỉ dùng một lần”, bài toán có thể vượt phạm vi một tài liệu. Khi đó cần thiết kế lại ranh giới document, unique index, transaction hoặc một quy trình idempotent có bằng chứng đúng đắn.

### 9.3. Quan hệ đến dữ liệu bên ngoài

“`productId` phải tồn tại”, “giá giảm không vượt giá hàng hiện tại” và “người dùng có quyền sửa tenant này” là những quy tắc phụ thuộc thực thể khác hoặc ngữ cảnh người gọi. Chúng không được giải quyết chỉ bằng JSON Schema trên tài liệu khuyến mãi.

Đối với dữ liệu tham chiếu có thể thay đổi, cần xác định **nguồn có thẩm quyền, thời điểm chốt dữ liệu, độ nhất quán và cách xử lý thay đổi đồng thời**. Một read model hoặc cache có thể đủ cho hiển thị, nhưng không phải lúc nào đủ cho hành động giao dịch.

## 10. Schema evolution: thay đổi quy tắc khi đã có dữ liệu

Document database thường được chọn vì khả năng tiến hóa cấu trúc. Chính điều đó làm schema validation cần một chiến lược triển khai rõ ràng.

Ví dụ phiên bản đầu:

~~~json
{
  "code": "NOVEMBER10",
  "amount": 10
}
~~~

Phiên bản mới:

~~~json
{
  "schemaVersion": 2,
  "code": "NOVEMBER10",
  "kind": "PERCENT",
  "amount": 10,
  "currency": null
}
~~~

Nếu ứng dụng mới yêu cầu `kind` trong mọi tài liệu ngay lập tức, dữ liệu cũ có thể không đạt validator. Trong khi đó một worker cũ vẫn có thể ghi tài liệu không có `kind`. Cần quản lý quá trình chuyển đổi.

### 10.1. Mô hình triển khai Expand → Migrate → Enforce

1. **Expand:** phát hành code đọc được cả hình dạng cũ và mới; tạm cho phép cả hai nếu cần. Ghi mới bắt đầu tạo field mới theo hợp đồng.
2. **Migrate/backfill:** chuyển tài liệu cũ theo batch an toàn, ghi checkpoint, thống kê tiến độ và các trường hợp không thể chuyển tự động.
3. **Enforce:** sau khi các phiên bản ứng dụng liên quan đã tương thích và dữ liệu tồn tại được xử lý, bật validator chặt hơn để từ chối bản ghi sai.
4. **Retire:** loại bỏ nhánh tương thích cũ khi chắc chắn không còn writer/reader cần nó.

Không yêu cầu “đổi schema một lần là xong” khi database có nhiều writer đang chạy. Rollout phải xử lý **thời gian các phiên bản cũ và mới cùng hoạt động**, kể cả consumer xử lý sự kiện cũ đến muộn.

### 10.2. Ví dụ về trường được đổi tên

Giả sử `discountPercent` được đổi thành `amount` kèm `kind`:

~~~text
V1: { discountPercent: 10 }
V2: { kind: "PERCENT", amount: Decimal128("10") }
~~~

Trong thời kỳ chuyển đổi, có một số lựa chọn:

- Reader mới hỗ trợ V1 và V2; writer mới chỉ ghi V2.
- Tạm hỗ trợ dual-write nếu thật sự cần writer/reader cũ, nhưng phải xử lý hai trường bất đồng.
- Backfill V1 sang V2 kèm kiểm tra số liệu.
- Chỉ sau đó siết validator và gỡ nhánh V1.

Gắn `schemaVersion` có thể hỗ trợ phân nhánh đọc và migration, nhưng **không tự đảm bảo mọi tài liệu đúng**. Validator vẫn cần mô tả phiên bản được phép hoặc kế hoạch chuyển đổi; dữ liệu dùng version sai phải được phát hiện.

### 10.3. Quy tắc mới có thể không hợp lệ với dữ liệu cũ

Một số sai lệch không thể sửa bằng cách gán giá trị mặc định:

- Tài liệu cũ không có `currency` nhưng tiền có thể là VND hoặc USD.
- Thời gian trước đây dùng múi giờ máy chủ mà không ghi offset.
- `amount` lúc là phần trăm, lúc là tiền; không có `kind`.
- `status` cũ không có sự kiện lịch sử để suy ra `publishedAt`.

Nếu không thể suy ra an toàn, cần giữ dữ liệu lịch sử với phiên bản riêng, đánh dấu “cần xử lý”, hoặc chạy quy trình hiệu chỉnh có chủ sở hữu. **Không tạo bừa giá trị mặc định để một tài liệu trông hợp lệ**.

## 11. Open schema hay closed schema?

Khi chọn mức chặt của validator, nên xác định dữ liệu thuộc loại nào.

| Loại tài liệu | Cách tiếp cận thường hữu ích | Lý do |
| --- | --- | --- |
| Đơn hàng, thanh toán, tồn kho | Kiểm tra chặt các field và bất biến quan trọng | Sai giá trị có hậu quả nghiệp vụ lớn |
| Hồ sơ tùy biến có nhiều thuộc tính | Giữ phần lõi chặt, phần mở rộng có cấu trúc | Hỗ trợ nhiều kiểu dữ liệu tùy ngữ cảnh |
| Event bất biến được phát đi | Schema version rõ ràng, tương thích reader | Consumer có thể xử lý event ở phiên bản khác nhau |
| Catalog sản phẩm nhiều category | Discriminator theo loại + schema cho từng nhóm | Mỗi loại sản phẩm có thuộc tính riêng |
| Log/telemetry | Field lõi thống nhất, không bắt buộc mọi metadata | Nguồn dữ liệu đa dạng và thay đổi nhanh |

Ví dụ thuộc tính mở rộng:

~~~json
{
  "productId": "P-42",
  "category": "BOOK",
  "name": "Cơ sở dữ liệu",
  "attributes": {
    "author": "A. Writer",
    "pageCount": 320
  }
}
~~~

Đối với `category = BOOK`, có thể cần `author` và `pageCount`. Đối với `category = ELECTRONICS`, cần `voltage` hoặc `warrantyMonths`. Đây là **conditional schema** theo discriminator. Tùy sản phẩm, có thể:

- Mô tả những dạng hợp lệ bằng biến thể schema được hỗ trợ.
- Sử dụng validator biểu thức cho quan hệ đơn giản.
- Đưa các kiểm tra phức tạp vào domain layer và database bảo vệ phần lõi.

Không nên dùng `Map<String, Object>` cho mọi thứ rồi bỏ hoàn toàn quy tắc: điều đó làm khó tìm kiếm, index, migration và khả năng dự đoán của API.

## 12. Các vấn đề khi cập nhật tài liệu

### 12.1. Ghi đè toàn bộ có thể làm mất field mới

Giả sử service A chạy bản cũ, đọc document rồi ghi đè toàn bộ; service B vừa thêm `publishedAt` hoặc `auditMetadata`. Nếu A ghi lại object cũ, những field mới có thể biến mất.

Biện pháp có thể gồm:

- Dùng cập nhật theo field (`$set` các field thật sự thay đổi) thay vì replace toàn bộ khi phù hợp.
- Dùng `version` và optimistic concurrency để tránh ghi đè bản đã thay đổi.
- Quản lý schema compatibility giữa các writer trong giai đoạn deploy.
- Đặt validator ở database để chặn mất field bắt buộc; nhưng **validator không chặn mất field tùy chọn hợp lệ** nếu không có quy tắc bổ sung.

### 12.2. Không tách các field phụ thuộc thành nhiều ghi thiếu nguyên tử

Nếu một đơn hàng đổi từ `DRAFT` sang `CONFIRMED`, đồng thời cần `confirmedAt`, hai lệnh tách rời có thể để lộ trạng thái tạm:

~~~text
UPDATE status = CONFIRMED
UPDATE confirmedAt = now()
~~~

Nếu validator yêu cầu `confirmedAt` với trạng thái CONFIRMED, lệnh đầu có thể bị từ chối. Đó là **tín hiệu hữu ích** rằng ứng dụng nên thay đổi các field phụ thuộc trong **cùng thao tác cập nhật nguyên tử** khi database hỗ trợ.

~~~javascript
db.orders.updateOne(
  { _id: "ORD-91", status: "DRAFT" },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
~~~

Đoạn này giả định phần còn lại của tài liệu hợp lệ và trạng thái CONFIRMED được phép từ DRAFT. Nếu lệnh trả `matchedCount = 0`, phải phân biệt không tìm thấy bản ghi với xung đột trạng thái và xử lý theo hợp đồng API.

### 12.3. Kiểm tra bất biến có thể phụ thuộc trạng thái trước

Một validator kiểm tra tài liệu cuối:

~~~text
status = ARCHIVED, archivedAt có giá trị  → hợp lệ
~~~

Nhưng nó không biết lệnh đổi từ `CANCELLED` sang `ARCHIVED` có được phép hay không, hoặc ai là người được thao tác. Điều kiện **`status` trước = DRAFT** nên được đưa vào bộ lọc atomic update khi nghiệp vụ yêu cầu; validator đảm nhận hình dạng cuối.

## 13. Kiểm thử validation có hệ thống

Một vài tài liệu insert thành công không đủ chứng minh hợp đồng. Các nhóm tình huống cần nghĩ tới:

| Nhóm | Ví dụ đầu vào | Kỳ vọng |
| --- | --- | --- |
| Missing | Không có `code` | Bị từ chối nếu bắt buộc |
| Null | `startsAt: null` | Bị từ chối khi yêu cầu BSON Date |
| Kiểu sai | `amount: "10"` | Bị từ chối khi yêu cầu Decimal128 |
| Biên số | `amount = -1`, `amount = 0`, `amount = 100`, `amount = 100.01` cho PERCENT | Phản ánh chính xác quy tắc biên |
| Biên thời gian | `startsAt == endsAt`; `startsAt > endsAt` | Bị từ chối nếu khoảng phải có thời lượng dương |
| Điều kiện trạng thái | `ACTIVE` thiếu `publishedAt` | Bị từ chối |
| Nested | `items` rỗng, thiếu `quantity`, sai kiểu một phần tử | Bị từ chối theo schema mảng |
| PATCH | Chỉ đổi `startsAt` làm khoảng thời gian cuối không hợp lệ | Bị từ chối tại miền nghiệp vụ/database |
| Cạnh tranh | Hai writer dùng cùng version hoặc cùng quota còn 1 | Chỉ các ghi thỏa điều kiện nguyên tử được chấp nhận |
| Backward compatibility | Tài liệu V1 qua reader V2; writer V1 trong rollout | Có kết quả đã định hoặc từ chối có chủ đích |
| Luồng ghi khác | Job import, consumer, script quản trị | Không vô tình tạo dữ liệu trái hợp đồng |

Có thể kiểm tra các quy tắc **đơn trường** và **cross-field** ở domain layer, rồi kiểm tra tích hợp với database thật cho những đặc tính liên quan BSON, validator, transaction, unique index và atomic update. Một mock object trong unit test không chứng minh driver đã serialize `BigDecimal` thành Decimal128 hoặc server đang thực thi validator đúng phiên bản.

**Đừng lẫn lộn validation với sửa dữ liệu**: nếu thiếu `kind`, không tự suy ra PERCENT chỉ vì `amount <= 100`; dữ liệu đó có thể là giảm 50.000 VND trên một đơn vị nhỏ. Việc migration phải có nguồn xác nhận để khôi phục ý nghĩa gốc.

## 14. Quan sát và vận hành schema validation

Validator càng chặt càng có giá trị, nhưng việc triển khai thiếu quan sát có thể biến một thay đổi schema thành lỗi ghi hàng loạt.

Các số liệu nên theo dõi:

- **Số thao tác ghi bị từ chối do validation**, phân theo service, collection, loại quy tắc và phiên bản ứng dụng.
- **Tỷ lệ tài liệu cũ không phù hợp** với schema mục tiêu khi chuẩn bị migration.
- **Tốc độ backfill, số bản ghi lỗi, retry và checkpoint** để tránh sửa đi sửa lại cùng dữ liệu.
- **Xung đột ghi/unique index/optimistic version** để phân biệt lỗi dữ liệu với tranh chấp thông thường.
- **Độ trễ và throughput ghi** sau khi thêm các validator phức tạp; biểu thức kiểm tra cũng có chi phí xử lý.
- **Mức tương thích reader/writer** trong giai đoạn các phiên bản cùng hoạt động.

Thông điệp lỗi nên đủ rõ để sửa đầu vào, ví dụ “`endsAt` phải sau `startsAt`” hoặc “`amount` phải từ 0 đến 100 khi `kind=PERCENT`”. Không nên công bố raw document chứa thông tin nhạy cảm trong log hay trả toàn bộ chi tiết nội bộ của database cho client.

Một chiến lược thay đổi an toàn thường là kiểm kê dữ liệu hiện tại, triển khai reader tương thích, có thể dùng chế độ quan sát vi phạm khi sản phẩm hỗ trợ, xử lý dữ liệu lịch sử rồi mới bật từ chối ghi. Phải xác nhận rằng toàn bộ đường ghi đã dùng phiên bản schema mới trước khi siết quy tắc.

### 14.1. Tài liệu schema là hợp đồng sống

Nên lưu một bản mô tả có phiên bản gồm:

~~~text
Collection: promotions
Schema version: 2
Required: code, kind, amount, startsAt, endsAt, status
Types: code string; kind enum; amount decimal; startsAt/endsAt date
Cross-field: startsAt < endsAt
Conditional: kind=PERCENT => amount <= 100
Conditional: status=ACTIVE => publishedAt là Date
Unique scope: (tenantId, code) qua unique index
State transition: DRAFT -> ACTIVE -> ARCHIVED
Concurrency: optimistic version hoặc atomic condition
Migration: quy tắc đọc/ghi V1 và V2, bước backfill
Owner: nhóm sở hữu domain promotions
~~~

Các dòng trên không phải cú pháp validator chạy được trực tiếp. Chúng là hợp đồng **để domain, API, database và migration cùng diễn giải một cách nhất quán**. Khi có nhiều service, cần biết bên nào sở hữu việc thay đổi hợp đồng đó.

## 15. Bài tập thực hành

Một ứng dụng quản lý đặt phòng lưu tài liệu:

~~~json
{
  "bookingId": "B-201",
  "roomId": "R-08",
  "checkIn": "2026-12-01T14:00:00Z",
  "checkOut": "2026-12-03T10:00:00Z",
  "status": "CONFIRMED",
  "confirmedAt": "2026-11-14T09:10:00Z",
  "guestCount": 2,
  "payment": {
    "currency": "VND",
    "totalMinor": 1800000
  }
}
~~~

Yêu cầu nghiệp vụ:

- Mỗi booking có `bookingId`, `roomId`, `checkIn`, `checkOut`, `status`, `guestCount`.
- `guestCount` là số nguyên dương; `checkIn < checkOut`.
- `status` thuộc `DRAFT`, `CONFIRMED`, `CANCELLED`.
- Khi `status = CONFIRMED`, `confirmedAt` phải tồn tại.
- Nếu `payment` có mặt, nó phải có `currency` và tổng tiền hợp lệ.
- Không cho phép hai booking **CONFIRMED** trùng cùng phòng và khoảng thời gian.

Hãy trả lời:

1. Những quy tắc nào diễn đạt được bằng `required`, kiểm tra kiểu, enum hoặc giới hạn số?
2. Những quy tắc nào bắt buộc so sánh **hai trường** trong cùng tài liệu?
3. Có thể dùng một validator trên mỗi booking để ngăn **hai booking khác nhau** trùng phòng và khoảng thời gian không? Nếu không, cần thay đổi quy trình đặt phòng hoặc cơ chế lưu trữ thế nào?
4. Với PATCH chỉ sửa `checkIn`, tại sao phải kiểm tra tài liệu sau cập nhật?
5. Nếu thay schema để `payment.currency` bắt buộc nhưng dữ liệu lịch sử chưa có trường này, bạn sẽ triển khai từng bước ra sao?
6. Khi hai request cùng xác nhận booking, làm thế nào để tránh cả hai đều vượt qua bước “kiểm tra phòng trống” rồi cùng commit?

**Hướng giải:** Hình dạng tài liệu và kiểu dữ liệu được schema bảo vệ; `checkIn < checkOut` và `CONFIRMED => confirmedAt` là quy tắc giữa trường; điều kiện **không trùng phòng theo khoảng thời gian** liên quan nhiều booking và cần mô hình đặt chỗ với thao tác nguyên tử/giao dịch, khóa logic hoặc cơ chế đồng bộ phù hợp. Kiểm tra tại API giúp trả lỗi rõ ràng, còn hàng rào ở database và cơ chế ghi đồng thời mới giúp chống dữ liệu sai từ những đường ghi khác.

Điểm quan trọng nhất của schema validation trong document NoSQL là **định nghĩa rõ những trạng thái được phép lưu, trong đó có quan hệ giữa các trường**. Khi quy tắc phụ thuộc dữ liệu cũ, tài liệu khác hay quyền người dùng, cần mở rộng từ schema sang **domain validation, unique index, atomic update và transaction**. Một document model linh hoạt chỉ phát huy lợi ích lâu dài khi tính linh hoạt ấy được quản lý bằng hợp đồng dữ liệu có thể kiểm tra và tiến hóa.
