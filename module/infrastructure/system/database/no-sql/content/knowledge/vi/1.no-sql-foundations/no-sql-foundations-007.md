# Schema linh hoạt, quy tắc dữ liệu và trách nhiệm kiểm tra đầu vào

Trong hệ quản trị quan hệ, cấu trúc bảng thường được khai báo trước bằng cột, kiểu dữ liệu và ràng buộc. Với nhiều cơ sở dữ liệu NoSQL, đặc biệt là **document database**, mỗi bản ghi có thể chứa những trường khác nhau. Đó là một lợi thế khi mô hình nghiệp vụ có nhiều biến thể hoặc thay đổi liên tục. Tuy nhiên, **schema linh hoạt không đồng nghĩa với dữ liệu không cần quy tắc**.

Một hệ thống có thể cho phép lưu bất kỳ JSON nào mà vẫn vận hành tốt lúc đầu. Vấn đề thường xuất hiện muộn hơn: một trường có lúc là số, có lúc là chuỗi; API đọc dữ liệu cũ không hiểu kiểu mới; báo cáo đếm sai; hai tiến trình cùng tạo một mã trùng nhau; hoặc một luồng nhập liệu bỏ qua kiểm tra của API. Bài toán thiết kế là quyết định **phần nào được linh hoạt, phần nào phải ổn định, ai chịu trách nhiệm thực thi từng quy tắc và thay đổi cấu trúc ra sao mà không làm hỏng dữ liệu đã tồn tại**.

## 1. Hiểu đúng về schema trong NoSQL

**Schema** là hợp đồng mô tả hình dạng và ý nghĩa của dữ liệu: trường nào tồn tại, có kiểu gì, giá trị nào hợp lệ, các trường liên quan đến nhau thế nào, và ứng dụng xử lý bản ghi qua các phiên bản ra sao.

Không nên đánh đồng ba khái niệm:

| Khái niệm | Ý nghĩa | Điểm cần nhớ |
|---|---|---|
| **Schema cố định (fixed schema)** | Cơ sở dữ liệu yêu cầu một cấu trúc tương đối thống nhất trước khi ghi dữ liệu. | Thay đổi thường đi qua quy trình sửa cấu trúc rõ ràng. |
| **Schema linh hoạt (flexible schema)** | Các bản ghi có thể khác nhau về tập trường hoặc cấu trúc lồng nhau. | Vẫn cần hợp đồng cho các trường quan trọng và các biến thể được hỗ trợ. |
| **Schema-on-read** | Một phần cấu trúc được diễn giải khi ứng dụng đọc hoặc phân tích dữ liệu. | Trách nhiệm chuyển sang bên đọc; sai khác về kiểu và phiên bản không tự biến mất. |

NoSQL là một nhóm rộng: key-value store, document database, wide-column store và graph database có mô hình cùng khả năng ràng buộc khác nhau. Ví dụ trong bài dùng **MongoDB** để minh họa document database, không ngụ ý mọi hệ NoSQL hỗ trợ cùng cú pháp, transaction hay JSON Schema.

### Ví dụ: hai loại sản phẩm trong cùng collection

Một cửa hàng có sách và thiết bị. Mọi sản phẩm đều có mã, tên, giá và loại; thông tin riêng thì khác nhau.

~~~javascript
// MongoDB / mongosh: tài liệu sách
{
  _id: "prd-001",
  sku: "BOOK-001",
  type: "book",
  name: "Nhập môn Java",
  priceMinor: NumberLong("189000"),
  currency: "VND",
  schemaVersion: NumberInt(2),
  attributes: {
    author: "Nguyễn An",
    isbn: "9786040000001"
  }
}

// Tài liệu thiết bị trong cùng collection products
{
  _id: "prd-002",
  sku: "DEVICE-001",
  type: "device",
  name: "Bàn phím cơ",
  priceMinor: NumberLong("850000"),
  currency: "VND",
  schemaVersion: NumberInt(2),
  attributes: {
    brand: "KeyLab",
    warrantyMonths: 12
  }
}
~~~

Ở đây, `sku`, `type`, `name`, `priceMinor`, `currency` và `schemaVersion` tạo thành **phần lõi ổn định**. `attributes` chứa dữ liệu theo từng loại sản phẩm. Trường phân biệt `type` giúp chương trình biết nên áp dụng quy tắc nào.

Quyết định thiết kế quan trọng là *lựa chọn những khác biệt có chủ đích*. Nếu sản phẩm có thể tùy ý thay `priceMinor` bằng `price`, `amount` hoặc một chuỗi như `"850.000đ"` thì đó là **schema drift** (trôi lệch cấu trúc), không phải một lợi ích có kiểm soát của NoSQL.

> Ví dụ dùng `priceMinor` là số nguyên biểu diễn đơn vị tiền nhỏ nhất mà hệ thống đã quy định. Với VND trong ví dụ, giá 189.000 VND được lưu thành 189000. Hệ thống hỗ trợ nhiều loại tiền cần xác định rõ quy tắc đơn vị nhỏ nhất theo từng loại; cũng có thể dùng số thập phân chính xác như MongoDB Decimal128. Tránh lưu tiền bằng kiểu dấu phẩy động không có chính sách làm tròn.

## 2. Vì sao cần linh hoạt, và giới hạn của sự linh hoạt

Schema linh hoạt hữu ích khi:

- **Thực thể có nhiều biến thể:** sách có ISBN, thiết bị có thời hạn bảo hành, quần áo có kích cỡ.
- **Thuộc tính không xuất hiện đồng đều:** địa chỉ giao hàng có thể cần trường tỉnh/bang tùy quốc gia; một số cấu hình chỉ áp dụng cho một nhóm khách hàng.
- **Mô hình thay đổi dần:** thêm một thuộc tính tùy chọn mà không cần sửa tất cả tài liệu cũ ngay lập tức.
- **Dữ liệu lồng nhau được đọc cùng nhau:** một document có thể chứa thông tin chi tiết phù hợp với nhu cầu truy vấn.

Nhưng mỗi mức linh hoạt đều có chi phí:

| Quyết định | Lợi ích | Rủi ro nếu thiếu hợp đồng |
|---|---|---|
| Trường tùy chọn | Hỗ trợ bản ghi cũ và nhu cầu không đồng nhất | Không phân biệt được `missing`, `null` và giá trị mặc định |
| Trường lồng nhau | Gom dữ liệu liên quan để đọc thuận tiện | Cấu trúc sâu, khó cập nhật hoặc kiểm soát kích thước |
| Thuộc tính theo loại | Mở rộng nhiều biến thể trong cùng collection | Ứng dụng đọc sai thuộc tính hoặc bỏ qua quy tắc theo loại |
| Dữ liệu phi chuẩn hóa (denormalized) | Giảm số lần truy vấn và phép nối tại thời điểm đọc | Bản sao có thể lệch nhau khi cập nhật |
| Cho phép nhiều phiên bản document | Triển khai thay đổi từng bước | Mã đọc phải hiểu phiên bản cũ trong giai đoạn chuyển đổi |

Một nguyên tắc hữu ích là **ổn định phần làm nên danh tính và bất biến nghiệp vụ; linh hoạt phần thực sự thay đổi theo biến thể**.

## 3. Thiết kế hợp đồng dữ liệu: lõi chung và phần mở rộng

Trước khi tạo collection, hãy mô tả các loại quy tắc cần áp dụng.

### 3.1. Quy tắc hình dạng và kiểu dữ liệu

Ví dụ cho collection `products`:

- `sku`: chuỗi không rỗng, dùng làm mã nghiệp vụ và không được trùng.
- `type`: chỉ nhận `book` hoặc `device` trong phạm vi ví dụ.
- `name`: chuỗi không rỗng.
- `priceMinor`: số nguyên không âm, lưu nhất quán bằng kiểu số đã chọn.
- `currency`: một mã tiền tệ đã được hệ thống hỗ trợ.
- `schemaVersion`: số nguyên cho biết cấu trúc bản ghi.
- `attributes`: object; nội dung phụ thuộc `type`.

Cần phân biệt **trường không có**, **trường có giá trị `null`** và **trường có giá trị hợp lệ như `0` hoặc chuỗi rỗng**. Chúng có thể mang ý nghĩa khác nhau. Chẳng hạn `warrantyMonths: 0` có thể nghĩa là không bảo hành; thiếu `warrantyMonths` lại có thể nghĩa là chưa nhập dữ liệu.

### 3.2. Quy tắc theo biến thể

Giả sử có hai quy tắc:

- Với `type = "book"`: cần `attributes.author` và `attributes.isbn`.
- Với `type = "device"`: cần `attributes.brand` và `attributes.warrantyMonths`, số tháng bảo hành là số nguyên không âm.

Không nên làm mọi trường trong `attributes` thành tùy chọn chỉ để dùng chung một DTO. Làm vậy khiến một tài liệu `device` thiếu thương hiệu hoặc lưu bảo hành bằng chuỗi vẫn đi qua các bước kiểm tra sơ sài.

Các phương án thường dùng:

1. **Hợp đồng cho từng loại:** mỗi loại có DTO/validator riêng và cùng được ánh xạ vào một document chung.
2. **Discriminator:** giữ `type` để phân nhánh xác thực và cách đọc.
3. **Schema registry hoặc hợp đồng có phiên bản:** hữu ích khi nhiều dịch vụ cùng sản xuất/tiêu thụ dữ liệu và cần công bố thay đổi.
4. **Vùng mở rộng có giới hạn:** chỉ cho phép các key/kiểu đã được khai báo; trường nào tham gia lọc, sắp xếp hoặc tính toán thường nên được quản lý chặt hơn một trường ghi chú.

### 3.3. Ranh giới document cũng là một lựa chọn thiết kế

NoSQL không mặc định rằng mọi quan hệ phải được nhúng vào cùng một document.

Ví dụ đơn hàng có thể lưu từng dòng hàng và **ảnh chụp tên, giá tại thời điểm mua** ngay trong đơn vì chúng thường được đọc cùng nhau và không nên đổi theo giá sản phẩm hiện tại. Mặt khác, `customerId` có thể tham chiếu khách hàng vì hồ sơ khách hàng là thực thể cập nhật độc lập.

Khi quyết định *embed* hay *reference*, cần xem:

- Dữ liệu nào thường được đọc hoặc cập nhật cùng nhau?
- Có cần cập nhật nguyên tử nhiều trường trong một document không?
- Một mảng lồng nhau có thể tăng không giới hạn không?
- Chấp nhận mức độ trùng lặp và chính sách đồng bộ nào?
- Cơ sở dữ liệu đang dùng hỗ trợ transaction và giới hạn kích thước document ra sao?

Lưu trữ cùng document có thể giúp nhiều thay đổi của chính document đó được thực hiện nguyên tử trong MongoDB. Quy tắc liên quan **nhiều document** vẫn cần chiến lược nhất quán và đồng thời riêng; không nên suy rộng tính nguyên tử từ một document thành toàn hệ thống.

## 4. Ai chịu trách nhiệm kiểm tra đầu vào?

Một lỗi phổ biến là hỏi “kiểm tra ở frontend hay database?”. Trên thực tế, từng tầng kiểm tra **những điều khác nhau** và hỗ trợ lẫn nhau.

| Tầng | Trách nhiệm chính | Ví dụ |
|---|---|---|
| **Giao diện/client** | Phản hồi sớm, hướng dẫn người dùng, giảm lỗi nhập liệu | Hiển thị “Vui lòng nhập tên”; cảnh báo giá âm |
| **API boundary / DTO** | Xác minh cấu trúc request, kiểu và giới hạn kích thước; từ chối trường không được phép | `priceMinor` phải là số nguyên; `sku` không rỗng; không nhận thuộc tính ngoài hợp đồng |
| **Domain/application service** | Thực thi bất biến nghiệp vụ, quy tắc theo loại và quyền thao tác | Thiết bị cần `brand`; người dùng chỉ sửa sản phẩm được phép |
| **Database** | Chốt các ràng buộc cần được bảo vệ trước mọi đường ghi có thể áp dụng tại DB | Validator về kiểu/trường bắt buộc; unique index cho `sku` |
| **Import, consumer, job nền** | Kiểm tra dữ liệu từ các nguồn không đi qua HTTP API; xử lý sự kiện sai hợp đồng | Chặn hoặc cách ly bản ghi CSV sai; kiểm tra version của event |
| **Luồng đọc và vận hành** | Đọc được phiên bản đang hỗ trợ; phát hiện dữ liệu cũ, dữ liệu lệch chuẩn và lỗi chuyển đổi | Adapter phiên bản, metrics về tài liệu sai schema |

Quy tắc ở **client** giúp trải nghiệm tốt nhưng không tạo hàng rào bảo vệ: request có thể đến từ script, service khác hoặc client cũ. Quy tắc ở **service** biểu diễn nghiệp vụ rõ ràng nhưng có thể bị bỏ qua bởi job ghi trực tiếp vào database. Ràng buộc ở **database** ngăn được một số trạng thái sai kể cả khi producer có lỗi, song không đủ ngữ cảnh để xác nhận mọi quy tắc nghiệp vụ.

Có thể hình dung luồng tạo sản phẩm như sau:

~~~mermaid
flowchart TD
    A[Client / nguồn dữ liệu] --> B[Kiểm tra request và quyền truy cập]
    B --> C{Hình dạng và kiểu hợp lệ?}
    C -- Không --> E[Trả lỗi 400, không ghi]
    C -- Có --> D[Kiểm tra quy tắc theo loại]
    D --> F{Thỏa bất biến nghiệp vụ?}
    F -- Không --> G[Trả lỗi nghiệp vụ]
    F -- Có --> H[Chuẩn hóa và ghi database]
    H --> I{Validator / unique index hợp lệ?}
    I -- Không --> J[Chuyển lỗi DB thành phản hồi phù hợp]
    I -- Có --> K[Lưu thành công]
~~~

### Một vài quy tắc không thể đặt vào một tầng duy nhất

**Tính duy nhất của `sku`.** Service có thể truy vấn “mã đã tồn tại chưa?” để trả thông báo thân thiện. Nhưng hai request chạy đồng thời đều có thể thấy mã chưa tồn tại. **Unique index tại database mới là điểm chặn cạnh tranh ghi**. Service cần bắt lỗi duplicate-key và trả phản hồi phù hợp (thường là HTTP 409 Conflict).

**Tính tồn tại của tham chiếu.** Khi lưu `customerId`, việc service đã kiểm tra khách hàng tồn tại không đảm bảo khách hàng không bị xóa trong thời điểm khác. Phải định nghĩa chính sách về xóa, quan hệ, giao dịch, trạng thái tham chiếu mồ côi và cách hòa giải. Không giả định mọi NoSQL tự cung cấp foreign key như cơ sở dữ liệu quan hệ.

**Quy tắc trên nhiều document.** Ví dụ “tổng tiền giữ chỗ không vượt hạn mức còn lại” cần giải quyết cập nhật đồng thời. Một phép đọc rồi ghi đơn giản có thể sai dù từng request đã được validate. Có thể cần cập nhật có điều kiện, optimistic concurrency, transaction được hệ quản trị hỗ trợ hoặc điều phối theo sự kiện với quy tắc bù trừ.

## 5. Ví dụ MongoDB: bảo vệ phần lõi bằng schema validation và index

MongoDB cho phép tạo collection với `$jsonSchema` validator. Đây là một cách đưa **phần hợp đồng cấu trúc tối thiểu** xuống tầng database.

~~~javascript
db.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "sku", "type", "name", "priceMinor",
        "currency", "schemaVersion", "attributes"
      ],
      properties: {
        sku:           { bsonType: "string", minLength: 1 },
        type:          { enum: ["book", "device"] },
        name:          { bsonType: "string", minLength: 1 },
        priceMinor:    { bsonType: "long", minimum: 0 },
        currency:      { enum: ["VND"] },
        schemaVersion: { bsonType: "int", minimum: 1 },
        attributes:    { bsonType: "object" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.products.createIndex({ sku: 1 }, { unique: true });
~~~

Ở ví dụ này:

- `required` bắt buộc tài liệu có trường tương ứng; quy tắc kiểu trong `properties` còn giúp loại giá trị sai kiểu.
- `bsonType: "long"` yêu cầu kiểu BSON số nguyên 64 bit cho giá; producer phải mã hóa đúng kiểu này, ví dụ `NumberLong("189000")` trong mongosh. Chuỗi `"189000"` không hợp lệ.
- `enum` giới hạn loại sản phẩm và đơn vị tiền được hỗ trợ trong *ví dụ*. Hệ thống thật phải lựa chọn danh sách theo yêu cầu nghiệp vụ.
- `validationLevel: "strict"` áp dụng kiểm tra đối với các thao tác ghi theo cơ chế validator của MongoDB; `validationAction: "error"` từ chối thao tác không thỏa điều kiện. Nếu dùng tùy chọn khác hoặc đặc quyền bỏ qua kiểm tra, cần hiểu tác động.
- `unique: true` áp đặt tính duy nhất của `sku`. Với môi trường sharding, kiểu index/khóa shard có thêm quy định; thiết kế phải kiểm tra theo cấu hình triển khai thực tế.

**Giới hạn có chủ ý:** validator trên mới xác minh `attributes` là một object. Nó **chưa** chứng minh sách có ISBN hoặc thiết bị có số tháng bảo hành phù hợp. Có thể mô hình hóa các nhánh phức tạp hơn bằng các cơ chế validation được DB hỗ trợ, nhưng quy tắc nghiệp vụ theo loại vẫn cần thể hiện rõ trong domain service. Đặc biệt, kiểm tra quyền sở hữu và quyền truy cập dữ liệu thường cần ngữ cảnh người dùng mà DB validator không có.

Nếu collection đã tồn tại, không gọi lại `createCollection` để “nâng cấp” schema; MongoDB có lệnh `collMod` để sửa validator theo quy trình phù hợp. Việc bổ sung validator không tự sửa các document cũ, và tạo unique index sẽ thất bại nếu dữ liệu hiện có đã chứa giá trị khóa trùng. Bởi vậy phải hiểu và xử lý dữ liệu hiện hữu trước khi siết ràng buộc.

### Ví dụ dữ liệu không hợp lệ

~~~javascript
{
  sku: "DEVICE-002",
  type: "device",
  name: "Chuột không dây",
  priceMinor: "350000",           // Sai: string thay vì BSON long
  currency: "VND",
  schemaVersion: NumberInt(2),
  attributes: {
    warrantyMonths: -12          // Sai quy tắc nghiệp vụ; thiếu brand
  }
}
~~~

Validator ở trên sẽ chặn vì `priceMinor` sai kiểu. Nếu sửa giá thành `NumberLong("350000")`, document vẫn **không thỏa hợp đồng nghiệp vụ của thiết bị**: thiếu `brand` và có `warrantyMonths` âm. Đây chính là lý do cần kiểm tra bổ sung theo `type` ở ứng dụng hoặc cấu hình thêm ràng buộc tương ứng ở DB.

## 6. Ví dụ Java/Spring Boot: kiểm tra tại biên API

Ở ứng dụng Java, một cách làm đơn giản là tạo request riêng cho biến thể có hợp đồng rõ ràng. Ví dụ endpoint tạo **thiết bị**:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateDeviceRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @PositiveOrZero Long priceMinor,
    @NotBlank String brand,
    @NotNull @Min(0) Integer warrantyMonths
) {}
~~~

Một controller dùng `@Valid @RequestBody CreateDeviceRequest request` để kích hoạt Bean Validation khi ứng dụng đã cấu hình nhà cung cấp validation phù hợp. Service chuyển DTO có kiểu rõ ràng thành document MongoDB với `type = "device"`, `attributes.brand` và `attributes.warrantyMonths`. Server tự xác định `schemaVersion`; không nên tin mọi metadata do client gửi.

Đoạn record mới thể hiện **kiểm tra cấu trúc**:

- `@NotBlank` đảm bảo trường chuỗi có nội dung sau khi bỏ qua khoảng trắng theo điều kiện của annotation.
- `@NotNull` tránh số dạng wrapper bị thiếu.
- `@PositiveOrZero` cho phép giá bằng 0 nếu nghiệp vụ cho phép.
- `@Min(0)` yêu cầu tháng bảo hành không âm.

Service vẫn cần kiểm tra các điều kiện mang nghĩa nghiệp vụ: độ dài và chuẩn hóa của SKU, chính sách giá, thương hiệu được phép, quy tắc ủy quyền; sau đó ánh xạ lỗi database (như trùng SKU) thành lỗi API nhất quán.

Với endpoint dùng chung cho nhiều loại sản phẩm, có thể dùng **typed polymorphic DTO** phân biệt bằng `type`. Nếu dùng `Map<String, Object>` để nhận `attributes`, phải có bước chuyển đổi và xác thực theo biến thể trước khi ghi. Một map nhận mọi giá trị mà không kiểm tra làm mất phần lớn lợi ích của hệ thống kiểu trong Java.

### Chuẩn hóa có khác với “sửa hộ” dữ liệu lỗi?

Ví dụ người dùng nhập SKU `" book-001 "`. Có thể công bố quy tắc chuẩn hóa thành `"BOOK-001"`, sau đó kiểm tra duy nhất. Quy tắc cần nhất quán với search và index; chỉ `trim` ở frontend nhưng không trim ở service có thể tạo hai danh tính khác nhau.

Ngược lại, không nên tự động ép `priceMinor: "abc"` thành `0` hay âm thầm thay `warrantyMonths: -1` bằng `0`. Đó là **thay đổi ý nghĩa** của dữ liệu, khiến lỗi nguồn vào khó phát hiện. Hãy trả thông báo có thể hành động:

~~~json
{
  "code": "INVALID_PRODUCT",
  "message": "Thông tin thiết bị không hợp lệ",
  "fields": [
    { "field": "warrantyMonths", "message": "Phải lớn hơn hoặc bằng 0" }
  ]
}
~~~

Đây là một **mẫu hợp đồng lỗi minh họa**, không phải định dạng lỗi mặc định của Spring Boot. Không phản hồi nguyên văn lỗi nội bộ hay thông tin nhạy cảm từ database ra client.

## 7. Phân loại quy tắc theo độ mạnh

Khi nói “dữ liệu hợp lệ”, phải phân biệt các cấp độ:

| Loại quy tắc | Câu hỏi cần trả lời | Ví dụ | Tầng thường chịu trách nhiệm |
|---|---|---|---|
| **Cú pháp** | Có đọc được payload không? | JSON đúng cú pháp, kích thước cho phép | API gateway/parser |
| **Cấu trúc** | Đúng trường và đúng kiểu không? | `priceMinor` là số nguyên; `type` là enum | DTO + DB validator |
| **Ngữ nghĩa** | Giá trị và tổ hợp trường có ý nghĩa không? | `device` phải có `brand`; hạn bảo hành không âm | Domain service, một phần DB |
| **Danh tính / duy nhất** | Có xung đột với bản ghi khác không? | Không trùng `sku` | Unique index + xử lý lỗi ở service |
| **Tham chiếu / liên tài liệu** | Mối quan hệ có nhất quán không? | `customerId` tồn tại theo chính sách | Service + cơ chế đồng thời/transaction |
| **Quyền truy cập** | Ai được phép thực hiện thao tác? | Chỉ chủ cửa hàng mới được đổi giá | AuthN/AuthZ ở API/service |
| **Tương thích phiên bản** | Producer và consumer có hiểu dữ liệu không? | Reader v2 hiểu document v1 | Mapper/adapter, giao kèo triển khai |

Cùng một dữ liệu có thể đúng kiểu nhưng sai nghiệp vụ. `warrantyMonths: 9999` là số nguyên không âm; nó vẫn có thể trái chính sách bảo hành. Ngược lại, một business rule hợp lý không thay thế được việc kiểm tra kiểu và nguồn đầu vào.

### Đừng quên dữ liệu đọc

Giả sử một ứng dụng đã lưu:

~~~json
{ "sku": "BOOK-OLD", "priceMinor": "189000" }
~~~

Nếu mã đọc hiện tại kỳ vọng số nguyên, query phân loại hoặc phép tính có thể không còn chính xác. Việc sửa validator hôm nay không làm quá khứ biến mất. Consumer nên có một trong ba chính sách rõ ràng: **đọc và chuyển đổi định dạng cũ được hỗ trợ**, **cách ly bản ghi sai để xử lý**, hoặc **từ chối kèm chỉ báo quan sát được**. Không lặng lẽ thay số liệu hoặc bỏ qua document mà không có chính sách.

## 8. Thay đổi schema mà vẫn đọc được dữ liệu cũ

Đây là điểm giao giữa ưu thế linh hoạt của NoSQL và trách nhiệm quản lý dữ liệu. Giả sử phiên bản cũ lưu `warrantyMonths` trực tiếp ở gốc document, còn phiên bản mới chuyển vào `attributes`.

**Phiên bản 1:**

~~~json
{
  "sku": "DEVICE-OLD",
  "type": "device",
  "warrantyMonths": 12,
  "schemaVersion": 1
}
~~~

**Phiên bản 2:**

~~~json
{
  "sku": "DEVICE-OLD",
  "type": "device",
  "attributes": {
    "warrantyMonths": 12,
    "brand": "KeyLab"
  },
  "schemaVersion": 2
}
~~~

Một trình đọc trong thời gian chuyển đổi có thể xử lý cả hai hình dạng:

~~~javascript
function getWarrantyMonths(document) {
  if (document.schemaVersion === 1) {
    return document.warrantyMonths;
  }
  if (document.schemaVersion === 2) {
    return document.attributes?.warrantyMonths;
  }
  throw new Error("Unsupported product schema version");
}
~~~

Ví dụ chỉ minh họa *adapter theo phiên bản*. Trong hệ thống thật, reader phải kiểm tra cả tính hợp lệ của kết quả và các trường bắt buộc, đồng thời quy định cách xử lý document không có `schemaVersion`.

### Trình tự chuyển đổi an toàn

1. **Công bố hợp đồng mới:** xác định trường mới, kiểu dữ liệu, trường bắt buộc và ý nghĩa của `schemaVersion`.
2. **Triển khai reader tương thích:** cho phép đọc phiên bản cũ và mới; bảo đảm các consumer liên quan đã được cập nhật.
3. **Chuyển writer:** bắt đầu sinh document theo phiên bản mới; nếu cần vận hành nhiều phiên bản dịch vụ đồng thời, thiết kế chiến lược đồng bộ hoặc ghi tương thích.
4. **Backfill dữ liệu cũ:** chuyển những document có thể chuyển đổi; ghi nhận trường hợp thiếu thông tin hoặc dữ liệu bẩn để xử lý có chủ đích.
5. **Quan sát và siết ràng buộc:** xác định không còn nguồn ghi cũ, thêm validator/index cần thiết; kiểm tra ảnh hưởng đến ứng dụng trước khi chặn kiểu cũ.
6. **Gỡ compatibility code khi đủ điều kiện:** chỉ sau khi dữ liệu và các consumer không còn phụ thuộc vào schema cũ.

Thêm trường mới **tùy chọn** thường ít rủi ro hơn đổi tên trường, đổi kiểu, đổi ý nghĩa hoặc làm một trường cũ trở thành bắt buộc. Một thay đổi có vẻ nhỏ, chẳng hạn chuyển `priceMinor` từ số sang chuỗi, có thể làm sai cả filter, sort, aggregation, index và phép tính.

**Bẫy thường gặp:** bật validator nghiêm ngặt chỉ chấp nhận v2 trước khi hoàn thành backfill. Các update hợp lệ về mặt nghiệp vụ đối với document v1 có thể bị từ chối vì chính document cũ không thỏa schema mới. Mức validation, dữ liệu tồn tại và trình tự rollout phải được thiết kế cùng nhau.

## 9. Quy tắc dữ liệu liên quan trực tiếp đến truy vấn và hiệu năng

Schema là hợp đồng cho cả **ghi** lẫn **đọc**.

Giả sử có các giá trị:

~~~json
{ "priceMinor": 90000 }
{ "priceMinor": 120000 }
{ "priceMinor": "90000" }
~~~

Một phép lọc số, sắp xếp hoặc tính tổng không có nghĩa là sẽ diễn giải chuỗi `"90000"` như số `90000`. Dữ liệu không đồng nhất kiểu có thể dẫn đến nhóm kết quả sai hoặc xử lý bổ sung khó dự đoán.

Các câu hỏi cần cân nhắc ngay khi thiết kế schema:

- Trường nào được lọc, sắp xếp hoặc tổng hợp thường xuyên? Chúng cần tên, kiểu và ý nghĩa ổn định.
- Index nào phục vụ các query chính? Index trên nhiều thuộc tính tùy ý có thể tăng chi phí lưu trữ và ghi.
- Document có thể phình lớn hoặc mảng lồng nhau tăng không giới hạn không? Cần cơ chế phân trang/tách thực thể khi thích hợp.
- Có lặp dữ liệu để tăng tốc đọc không? Nếu có, **bản nào là nguồn sự thật**, khi nào cập nhật bản sao và cách phát hiện lệch?
- Có truy vấn theo `attributes` của từng `type` không? Có thể cần index riêng, partial index hoặc tách collection tùy tần suất truy vấn và giới hạn của hệ DB.

Không phải cứ cùng loại tài liệu là phải chung collection. Khi các biến thể có vòng đời, truy vấn, chính sách bảo mật và khả năng tăng trưởng rất khác nhau, tách collection có thể làm hợp đồng rõ và index gọn hơn.

## 10. Đường ghi không chỉ có HTTP API

Trong hệ thống thực tế, dữ liệu có thể đến từ form, mobile app, import CSV, message broker, job đồng bộ, script quản trị hoặc service nội bộ.

Vì vậy, câu “đã validate ở controller” chưa đủ. Hãy xác định từng **đường ghi**:

- **HTTP request:** validate payload, xác thực/quyền truy cập, kiểm tra nghiệp vụ, rồi ghi.
- **Import hàng loạt:** parse/validate từng dòng; giữ báo cáo lỗi, phân biệt dòng bị từ chối và dòng được nhận; quyết định có cho phép nhập một phần hay không.
- **Consumer sự kiện:** xác minh version, payload và idempotency; xử lý trùng event và retry để không nhân đôi bản ghi.
- **Job sửa dữ liệu:** tuân thủ hợp đồng mới, ghi audit và có phương án xử lý bản ghi không thể chuyển đổi.
- **Truy cập database trực tiếp:** giới hạn quyền ghi và dùng validator/index tương ứng với mức bảo vệ cần thiết.

Khi nguồn dữ liệu không đáng tin cậy, kiểm tra cả **giới hạn độ dài, độ sâu, số phần tử, key cho phép và kiểu**. Ví dụ, không nên ghép đối tượng lọc do client tự gửi thẳng thành toán tử MongoDB; ứng dụng nên xây dựng query từ các trường và phép toán được cho phép. Điều này vừa bảo vệ an toàn truy vấn, vừa tránh client vô tình hoặc cố ý tạo những query quá đắt.

## 11. Một tình huống tổng hợp: thêm sản phẩm “khóa học số”

Hệ thống hiện có `book` và `device`. Đội sản phẩm muốn thêm `digitalCourse` với `attributes.durationMinutes` và `attributes.accessDays`.

Nếu chỉ thêm giá trị `"digitalCourse"` vào một document mẫu rồi ghi xuống database, có thể xảy ra:

1. Validator đang giới hạn `type` ở hai loại cũ, nên document bị từ chối.
2. DTO hoặc service dùng enum cũ và không hiểu loại mới.
3. Màn hình chi tiết chỉ biết cách hiển thị thông tin sách hoặc thiết bị.
4. Báo cáo doanh thu lọc theo `type` cố định nên bỏ sót khóa học số.
5. Consumer event có thể không hiểu cấu trúc mới dù bản ghi đã lưu thành công.

Một thay đổi hoàn chỉnh cần thiết kế **hợp đồng của biến thể mới**:

| Thành phần | Điều cần quyết định |
|---|---|
| Dữ liệu lõi | Giữ `sku`, `name`, `priceMinor`, `currency`, `schemaVersion` với kiểu không đổi |
| Thuộc tính riêng | `durationMinutes`, `accessDays`: kiểu nguyên dương hay cho phép 0? Bắt buộc trong trường hợp nào? |
| Kiểm tra API | Bổ sung DTO/validator của `digitalCourse` và thông báo lỗi tương ứng |
| Database | Mở rộng tập `type` hợp lệ và các ràng buộc khác nếu cần |
| Reader/query | Bổ sung cách hiển thị, xử lý/filter/index phù hợp |
| Dữ liệu cũ | Tài liệu loại cũ vẫn đọc được; không bắt chúng phải có trường riêng của loại mới |
| Tích hợp | Thống nhất cách producer/consumer nhận biết loại và phiên bản |

Cách nhìn này giải thích vì sao thay đổi schema trong NoSQL đôi khi đơn giản ở **thao tác lưu** nhưng vẫn là một thay đổi có phạm vi ở **hợp đồng hệ thống**.

## 12. Các phản ví dụ đáng ghi nhớ

**“NoSQL nên mọi field đều optional.”** Nếu mã sản phẩm, giá hay loại sản phẩm có thể vắng mặt tùy ý, mỗi reader buộc phải tự đoán ý nghĩa. Hãy phân biệt thuộc tính tùy chọn có chủ đích với dữ liệu thiếu do lỗi.

**“Đã validate ở frontend là đủ.”** API khác, script và job có thể vượt qua frontend. Ranh giới server phải tự bảo vệ hợp đồng của mình.

**“DB validator giải quyết toàn bộ nghiệp vụ.”** Validator phù hợp với một số ràng buộc dữ liệu, nhưng không tự biết quyền người dùng, quy trình phê duyệt hay tất cả điều kiện xuyên nhiều tài liệu.

**“Service kiểm tra SKU trước thì không thể trùng.”** Hai request đồng thời có thể cùng vượt qua phép kiểm tra. Ràng buộc unique ở DB mới chặn xung đột ghi trong phạm vi mà index đảm bảo.

**“Schema linh hoạt nghĩa là có thể đổi kiểu bất cứ lúc nào.”** Dữ liệu trộn số và chuỗi gây ảnh hưởng trực tiếp lên phép tính, query, index, thống kê và deserialization.

**“Thêm validator sẽ sửa hết dữ liệu cũ.”** Validator điều khiển việc chấp nhận thao tác ghi theo cấu hình; dữ liệu tồn tại cần kế hoạch kiểm kê, chuyển đổi và xử lý lỗi riêng.

**“Cứ nhúng hết để tránh JOIN.”** Một document quá lớn hoặc cập nhật thường xuyên bởi nhiều luồng có thể làm giảm hiệu quả và gây tranh chấp. Ranh giới document phải theo cách truy cập và tính nhất quán mong muốn.

## 13. Cách tư duy khi gặp một yêu cầu mới

Thay vì hỏi đầu tiên “collection này có cho phép thêm field không?”, hãy lần lượt trả lời các câu hỏi:

1. **Danh tính của bản ghi là gì?** Trường nào định danh và phải duy nhất?
2. **Quy tắc bất biến là gì?** Kiểu, miền giá trị, mối liên hệ giữa các trường và giới hạn kích thước nào phải được bảo vệ?
3. **Biến thể nào thực sự được hỗ trợ?** Phần nào chung, phần nào riêng theo `type`?
4. **Ai có thể ghi?** Bao gồm API, event, import, migration và công cụ quản trị.
5. **Ai có thể đọc?** Phiên bản client/service nào và kiểu truy vấn nào phải tiếp tục hoạt động?
6. **Nếu hai thao tác chạy đồng thời thì sao?** Điều kiện nào phải được bảo vệ bằng index, cập nhật có điều kiện hoặc transaction?
7. **Khi schema đổi thì triển khai thế nào?** Reader, writer, backfill, validator và thời điểm xóa tương thích được phối hợp ra sao?

Một hợp đồng NoSQL có trách nhiệm thường có dạng:

~~~text
Phần lõi ổn định
  + Các biến thể được định nghĩa rõ
  + Quy tắc ở biên API và tầng nghiệp vụ
  + Ràng buộc database đối với bất biến cần bảo vệ
  + Cơ chế đọc nhiều phiên bản và chuyển đổi dữ liệu
  + Quan sát các đường ghi ngoài API
= Linh hoạt có kiểm soát
~~~

Điểm cốt lõi của tư duy NoSQL là **chủ động chọn nơi áp dụng cấu trúc và ràng buộc**. Database có thể cho phép hai document khác nhau; điều đó không có nghĩa ứng dụng được phép hiểu hai document ấy theo hai cách mâu thuẫn. Thiết kế tốt giữ được sự linh hoạt để phát triển sản phẩm, đồng thời duy trì dữ liệu đáng tin cậy cho những chương trình đọc, ghi và phân tích nó.
