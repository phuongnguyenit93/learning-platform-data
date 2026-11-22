# Quy ước định danh, tên trường và tài liệu hóa hợp đồng

NoSQL thường được mô tả là cơ sở dữ liệu có **schema linh hoạt**. Điều này không có nghĩa ứng dụng được phép lưu cùng một thuộc tính bằng nhiều tên và kiểu tùy ý. Khi API, worker, job import và dịch vụ phân tích cùng sử dụng một collection, tên trường và kiểu dữ liệu trở thành **hợp đồng chung**. Một bên đổi tên `priceMinor` thành `priceAmount` có thể vẫn ghi thành công, nhưng bên khác tiếp tục đọc trường cũ và tính sai kết quả.

Ba câu hỏi cốt lõi khi thiết kế:

1. **Định danh:** Bản ghi được nhận diện bằng khóa nào? Khóa đó có bất biến, duy nhất và được sử dụng thống nhất không?
2. **Tên trường và kiểu:** Giá trị có ý nghĩa gì, được biểu diễn bằng BSON/JSON type nào, có đơn vị và trạng thái thiếu/null ra sao?
3. **Hợp đồng:** Ai sở hữu, ghi, đọc, kiểm tra và thay đổi cấu trúc? Làm sao đưa phiên bản mới vào mà không phá ứng dụng cũ?

Bài học thuộc chủ đề **Kiểu dữ liệu và schema** trong **Database No SQL**. Ví dụ kỹ thuật sử dụng MongoDB, BSON và Java/Spring; các nguyên tắc còn có thể áp dụng cho các hệ document, key-value và NoSQL phân tán khác. Hãy kiểm tra quy tắc index, validator, transaction và sharding của hệ quản trị thực tế trước khi áp dụng.

## 1. Một document trông đơn giản nhưng chứa nhiều hợp đồng

Giả sử nền tảng bán hàng đa tenant lưu document:

~~~javascript
{
  _id: "prod_01J9QK7M8X6V2N3P4R5T6W7Y8Z",
  tenantId: "shop-17",
  sku: "kb-red",
  skuKey: "KB-RED",
  name: "Bàn phím cơ màu đỏ",
  status: "ACTIVE",
  price: {
    amountMinor: NumberLong("350000"),
    currency: "VND"
  },
  tags: ["keyboard", "mechanical"],
  dimensions: {
    widthMm: 360,
    heightMm: 42,
    depthMm: 130
  },
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: ISODate("2026-11-14T08:00:00Z"),
  schemaVersion: 2
}
~~~

Các câu hỏi cần trả lời không xuất hiện trực tiếp từ tên BSON:

- `_id` có được công khai làm ID ở API hay chỉ dùng nội bộ?
- `tenantId` có phải lấy từ người gọi đã xác thực không?
- `sku` có được đổi không; `skuKey` chuẩn hóa bằng thuật toán nào?
- Hai cửa hàng có được cùng dùng `KB-RED` không?
- `price.amountMinor` là số nguyên 64 bit; currency có thay đổi theo mỗi sản phẩm không?
- `tags` có thể không tồn tại trong document cũ, có thể là `null` không?
- `createdAt` và `updatedAt` do client hay server cấp?
- Reader schema v1 có hiểu `price` ở schema v2 không?

Nếu không ghi những quy tắc này, “schema linh hoạt” có thể trở thành **schema drift**: dữ liệu vẫn được lưu nhưng những producer/consumer hiểu khác nhau.

### Các lớp hợp đồng

~~~mermaid
flowchart TD
    A["HTTP API / Events"] --> B["Request validation và DTO"]
    B --> C["Domain invariants + ownership"]
    C --> D["Persistence mapping"]
    D --> E["NoSQL document + index + validator"]
    E --> F["Read model, cache, analytics"]
    G["Data contract + version + migrations"] --> A
    G --> B
    G --> C
    G --> D
    G --> E
    G --> F
~~~

Một hợp đồng đầy đủ có bốn lớp: **cấu trúc**, **ngữ nghĩa**, **quyền sở hữu** và **tiến hóa**. Storage validator có thể bảo vệ nhiều quy tắc cấu trúc, nhưng không thay thế hoàn toàn domain logic, authorization hoặc chiến lược migration.

## 2. Các loại khóa không nên bị đánh đồng

| Khóa | Vai trò | Ví dụ | Quy tắc quan trọng |
|---|---|---|---|
| **ID kỹ thuật** | Nhận diện thực thể ổn định | `_id`, UUID | Không đổi khi tên hay mã nghiệp vụ đổi |
| **Khóa nghiệp vụ** | Mã người dùng/hệ ngoài nhận biết | SKU, employeeCode | Có thể đổi; scope unique phải rõ |
| **Khóa chuẩn hóa** | So sánh nghiệp vụ nhất quán | `skuKey` | Cùng thuật toán ở mọi writer |
| **Khóa phạm vi** | Xác định chủ sở hữu hoặc namespace | `tenantId` | Phải được kiểm tra quyền |
| **Khóa tham chiếu** | Trỏ tới thực thể liên quan | `customerId`, `productId` | Giữ loại ID và scope thống nhất |
| **External ID** | Ánh xạ danh tính bên ngoài | `externalOrderId` | Thường cần provider/account nguồn |
| **Idempotency key** | Nhận biết request được gửi lại | `requestId` | Cùng ý định phải có cùng key |
| **Partition/shard key** | Phân phối dữ liệu và tải | `tenantId`, khóa tổng hợp | Chọn theo access pattern, không chỉ unique |

Một field có thể phục vụ nhiều mục đích, nhưng **có ID duy nhất không đồng nghĩa có shard key tốt**, và **khóa nghiệp vụ có vẻ duy nhất không mặc nhiên là định danh bất biến**.

### Identity khác thuộc tính hiện tại

Một Product đổi tên hoặc SKU vẫn có thể là cùng Product. Nếu dùng tên sản phẩm làm khóa tham chiếu, một lần đổi tên có thể làm đứt liên kết. Nếu dùng ID ổn định, các OrderLine cũ vẫn trỏ đúng Product ngay cả khi danh mục thay đổi.

**ID không phải mật khẩu.** Dù UUID khó đoán, API vẫn phải kiểm tra người gọi có quyền đối với ID và tenant đó không.

## 3. Chọn định dạng ID và giữ nguyên kiểu

Các định dạng thường gặp:

| Định dạng | Ưu điểm | Cân nhắc |
|---|---|---|
| UUID v4 | Sinh phân tán, không cần counter tập trung | Kích thước và ảnh hưởng đến locality của index |
| UUID v7 | Có thành phần thời gian, sắp xếp gần thời gian | Không đảm bảo thứ tự tuyệt đối qua mọi node |
| ULID | Chuỗi có thể sắp xếp theo thời gian nếu sinh đúng | Clock, encoding, tính đơn điệu và độ duy nhất |
| MongoDB ObjectId | Tích hợp BSON và MongoDB driver | Không nên xem là secret hoặc timestamp chính xác tuyệt đối |
| Số tăng dần | Ngắn, dễ đọc | Bộ cấp số có thể thành điểm nghẽn; ID dễ đoán |
| Prefix + opaque ID | Phân biệt loại thực thể như `prod_...` | Prefix không tự bảo đảm độ duy nhất |

Trong tài liệu này, `_id` là **BSON string** với prefix `prod_`. Nếu dự án chọn BSON ObjectId thì phải ghi rõ điều đó và thống nhất giữa writer, reader và API mapper.

Hai document:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011") }
{ _id: "507f1f77bcf86cd799439011" }
~~~

có `_id` với hai **kiểu BSON khác nhau**. Query dùng string không tương đương query dùng ObjectId:

~~~javascript
db.products.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});

db.products.findOne({
  _id: "507f1f77bcf86cd799439011"
});
~~~

Không được tự chuyển đổi ID bằng cách nối chuỗi rồi mặc định mọi document đều dùng cùng kiểu. Khi import/merge dữ liệu, contract cần bảo vệ uniqueness, ánh xạ ID cũ–mới và mọi reference liên quan.

### Một hay hai ID?

Có hệ thống lưu cả `_id` nội bộ và `productId` công khai. Cách này có lý do khi muốn thay công nghệ lưu trữ mà không đổi ID API, hoặc khi hai lớp ID có vòng đời khác nhau. Nhưng nó cũng tạo thêm index và nghĩa vụ giữ mapping nhất quán.

Nếu `_id` đủ phù hợp, có thể dùng một identity ổn định, rồi ánh xạ ở boundary:

~~~text
Storage:  _id = "prod_01..."
API JSON: id = "prod_01..."
Event:    productId = "prod_01..."
~~~

Các tên field có thể khác giữa các boundary, nhưng phải cùng chỉ **một định danh thực thể**.

## 4. Phạm vi duy nhất của business key

“SKU unique” là một câu chưa đủ để thiết kế index. Trong hệ thống đa tenant, hai cửa hàng có thể cùng đặt SKU `KB-RED`.

Một quy tắc rõ ràng:

> Hai Product khác nhau thuộc cùng `tenantId` không được có cùng `skuKey`.

Tương ứng với tổ hợp khóa `(tenantId, skuKey)`. Tùy nghiệp vụ, quy tắc có thể áp dụng cho mọi Product, chỉ Product ACTIVE hoặc cả các mã từng được cấp trong lịch sử.

Ví dụ:

| Trường hợp | Có thể hợp lệ? |
|---|---|
| Shop A, SKU KB-RED; Shop B, SKU KB-RED | Có, nếu unique theo tenant |
| Shop A, hai Product ACTIVE cùng SKU KB-RED | Không |
| Shop A, Product ARCHIVED rồi tạo Product khác cùng SKU | Tùy chính sách tái sử dụng mã |
| Hai provider cùng dùng externalOrderId `123` | Có, nếu ID chỉ duy nhất trong từng provider |
| Hai booking cùng ghế nhưng khác suất chiếu | Có |
| Hai booking hiệu lực cùng ghế và cùng suất chiếu | Không, theo bất biến đặt chỗ |

Cũng cần phân biệt **tính duy nhất của khóa** và **idempotency của thao tác**. Unique index trên SKU giúp chặn hai Product trùng, nhưng nếu client gửi lại cùng request sau timeout, server còn cần quyết định trả kết quả cũ hay báo conflict. Idempotency có contract riêng về namespace, thời hạn và payload.

## 5. Chuẩn hóa business key trước khi so sánh

Các chuỗi:

~~~text
"KB-RED"
"kb-red"
" KB-RED "
~~~

có thể có cùng ý nghĩa SKU. Không nên để mỗi service tự chọn cách so sánh.

Một chính sách SKU ASCII minh họa:

1. Trim khoảng trắng đầu/cuối.
2. Chuyển chữ cái Latin thành in hoa.
3. Chỉ cho phép `A-Z`, `0-9` và dấu gạch nối.
4. Giới hạn tối đa 40 ký tự.
5. Lưu `sku` để hiển thị, `skuKey` để so sánh/unique.

~~~java
import java.util.Locale;
import java.util.regex.Pattern;

public final class SkuKey {
    private static final Pattern ALLOWED =
        Pattern.compile("[A-Z0-9-]{1,40}");

    private SkuKey() {}

    public static String from(String value) {
        if (value == null) {
            throw new IllegalArgumentException("SKU required");
        }

        String key = value.strip().toUpperCase(Locale.ROOT);

        if (!ALLOWED.matcher(key).matches()) {
            throw new IllegalArgumentException("Invalid SKU");
        }

        return key;
    }
}
~~~

Quy tắc trên chỉ phù hợp mã SKU theo bảng ký tự đã chọn. Không dùng nguyên xi cho email, tên người hay Unicode tổng quát. Khi hỗ trợ Unicode, cần quy định normalization, case folding, locale và ký tự nhìn giống nhau. Việc đổi thuật toán có thể làm hai mã cũ trở thành trùng sau chuẩn hóa; migration phải nhận diện và xử lý collision.

## 6. Đặt tên collection và field theo một quy ước nhất quán

Một dự án Java + MongoDB có thể chọn:

| Thành phần | Quy ước gợi ý | Ví dụ |
|---|---|---|
| Collection | Danh từ số nhiều, chữ thường | `products`, `orders` |
| Field | `lowerCamelCase` | `tenantId`, `createdAt` |
| Reference ID | Hậu tố `Id` | `customerId`, `providerId` |
| Khóa so sánh | Hậu tố `Key` | `skuKey`, `usernameKey` |
| Timestamp | Hậu tố `At` | `confirmedAt`, `expiresAt` |
| Ngày lịch | Hậu tố `Date` | `birthDate`, `dueDate` |
| Duration | Đơn vị trong tên | `timeoutMs`, `leaseSeconds` |
| Kích thước/khoảng cách | Đơn vị rõ ràng | `sizeBytes`, `distanceMeters` |
| Tiền | Giá trị và đơn vị | `price.amountMinor` + `currency` |
| Boolean | Tên mệnh đề đúng/sai | `isPublished`, `requiresApproval` |
| Enum | Mã trạng thái ổn định | `status: "ACTIVE"` |
| Mảng | Danh từ số nhiều | `tags`, `orderLines` |
| Version | Nêu loại version | `schemaVersion`, `aggregateVersion` |

CamelCase hay snake_case đều có thể dùng nếu các bên thống nhất và có mapper phù hợp. Tránh một collection lưu `created_at`, một collection khác lưu `createdAt` cho cùng ý nghĩa mà không có lý do.

### Tránh tên quá chung

`value`, `data`, `flag`, `time`, `date`, `price` đôi khi không đủ để hiểu kiểu và ý nghĩa. Chẳng hạn `timeout` không cho biết mili giây hay giây; `price` không cho biết currency và quy tắc làm tròn.

### Dấu chấm và dấu dollar trong tên field

MongoDB sử dụng dấu chấm để truy cập **đường dẫn lồng nhau**, còn dấu `$` liên quan cú pháp toán tử. Một số phiên bản cho phép lưu field có các ký tự đó trong những ngữ cảnh nhất định, nhưng vẫn có giới hạn và khó khăn khi truy vấn, import/export hoặc dùng công cụ.

Đối với field thông thường, nên tránh tên literal chứa `.` hoặc bắt đầu bằng `$` để không nhầm với query path và operator. Ví dụ nên lưu:

~~~json
{
  "contact": {
    "email": "demo@example.invalid"
  }
}
~~~

thay vì lưu một key có tên nguyên văn `"contact.email"` nếu mục tiêu là object lồng nhau.

## 7. Đường dẫn lồng nhau là một phần hợp đồng

Những trường cùng mô tả một value object có thể được nhóm:

~~~javascript
{
  price: {
    amountMinor: NumberLong("350000"),
    currency: "VND"
  },
  dimensions: {
    widthMm: 360,
    heightMm: 42,
    depthMm: 130
  }
}
~~~

Truy vấn dùng dot notation:

~~~javascript
db.products.find({
  "price.currency": "VND",
  "price.amountMinor": { $gte: NumberLong("300000") }
});
~~~

Đổi từ `price.amountMinor` sang `price.minorUnits` có thể ảnh hưởng query, index, aggregation, mapping, API và consumer. Vì vậy **rename field không chỉ là refactor biến Java**.

Một object lồng nhau cũng cần định nghĩa nullability: `price` bắt buộc là object hay có thể null? Nếu price có object nhưng thiếu currency, hành vi thế nào?

## 8. BSON type khác JSON type

JSON thường dùng string, number, boolean, array, object và null. MongoDB dùng **BSON**, có các loại bổ sung: ObjectId, Date, Int32, Int64, Decimal128, binary và nhiều loại khác.

| Ý nghĩa | Kiểu lưu phù hợp | Lưu ý |
|---|---|---|
| ID dạng chuỗi | BSON string | Không trộn với ObjectId |
| Số lượng | BSON int hoặc long | Ghi rõ giới hạn và kiểu Java |
| Tiền đơn vị nhỏ nhất | BSON long | Có currency và quy tắc scale |
| Số thập phân chính xác | Decimal128 tùy nghiệp vụ | Tránh mất độ chính xác do double |
| Thời điểm tuyệt đối | BSON Date | Quy ước UTC và timezone hiển thị |
| Cờ | BSON bool | False khác missing |
| Enum | BSON string | Code cố định, tránh nhãn dịch |
| Danh sách | BSON array | Kiểu phần tử, độ dài và thứ tự |
| Giá trị lồng nhau | BSON object | Validator cho các field con |
| Binary | BSON binary hoặc storage ngoài | Cân nhắc kích thước, bảo mật |

Trong JavaScript, `Number` có giới hạn độ chính xác nguyên an toàn; BSON Int64 có miền lớn hơn. Khi trao đổi qua HTTP JSON cho client JavaScript, nếu số nguyên có thể vượt miền an toàn, cần một chính sách serialization rõ (chẳng hạn string cho một số giá trị), không tự chuyển mọi Int64 thành JavaScript number.

### BSON Extended JSON chỉ là cách biểu diễn có kiểu

~~~json
{
  "price": {
    "amountMinor": { "$numberLong": "350000" },
    "currency": "VND"
  },
  "createdAt": {
    "$date": "2026-11-14T08:00:00Z"
  }
}
~~~

Đây là ví dụ Extended JSON. API HTTP công khai không bắt buộc phải trả đúng cấu trúc Extended JSON này; cần một **API contract riêng**.

## 9. Quy ước đơn vị và số tiền

Một field số không có đơn vị rõ ràng dễ gây sai logic:

~~~javascript
{
  timeoutMs: 3000,
  leaseSeconds: 45,
  distanceMeters: 5000,
  widthMm: 360,
  temperatureC: 24.5,
  sizeBytes: NumberLong("1048576")
}
~~~

Nếu đơn vị có thể thay đổi theo đối tượng, có thể dùng object:

~~~json
{
  "serviceRadius": {
    "value": 5,
    "unit": "km"
  }
}
~~~

Mỗi cách có đánh đổi. Hậu tố đơn vị đơn giản và dễ query khi đơn vị cố định; object đơn vị linh hoạt nhưng cần validation và quy tắc quy đổi.

Với tiền:

~~~javascript
{
  price: {
    amountMinor: NumberLong("350000"),
    currency: "VND"
  }
}
~~~

Cần xác định định nghĩa minor unit theo currency và nghiệp vụ, không mặc định mọi tiền tệ có hai chữ số thập phân. Không cộng hai giá trị khác currency chỉ vì cùng kiểu số.

Đổi `timeoutSeconds` sang `timeoutMs` không chỉ là rename: phải nhân hệ số thích hợp, kiểm tra rounding/overflow và cập nhật mọi consumer.

## 10. Thời gian phải có ngữ nghĩa rõ

| Field | Ý nghĩa thường dùng |
|---|---|
| `createdAt` | Thời điểm tạo record/thực thể |
| `updatedAt` | Thời điểm bản ghi được cập nhật |
| `confirmedAt` | Thời điểm nghiệp vụ xác nhận |
| `eventTime` | Thời điểm sự kiện xảy ra tại nguồn |
| `ingestedAt` | Thời điểm hệ thống nhận sự kiện |
| `effectiveFrom` | Thời điểm quy tắc bắt đầu hiệu lực |
| `expiresAt` | Thời hạn hết hiệu lực |
| `deletedAt` | Thời điểm xóa mềm |
| `birthDate` | Ngày lịch, không nhất thiết kèm giờ |

Thời điểm tuyệt đối thường nên lưu bằng BSON Date và sử dụng UTC, sau đó chuyển múi giờ tại tầng hiển thị. Không lưu `"14/11/2026 15:00"` mà không biết timezone rồi mong các bên tự hiểu đúng.

**Ngày lịch** như ngày sinh có semantics khác một timestamp. Có thể dùng chuỗi ISO `YYYY-MM-DD` hoặc kiểu riêng, kèm quy tắc chuyển đổi nếu cần.

### Event time khác ingestion time

Một thiết bị ghi sự kiện lúc 08:00 nhưng offline đến 09:00 mới gửi. Nếu dashboard hỏi “sự kiện xảy ra lúc nào?”, cần `eventTime`; nếu hỏi “hệ thống nhận dữ liệu lúc nào?”, dùng `ingestedAt`. Một field `createdAt` mơ hồ có thể gây sai báo cáo.

### TTL không đồng nghĩa với deadline nghiệp vụ

Nếu reservation hết hạn lúc 10:00, code xử lý đặt hàng phải kiểm tra thời hạn trong đường ghi thích hợp. TTL cleanup có thể chạy nền, không bảo đảm xóa document đúng mili giây.

## 11. Null, missing, empty và false không giống nhau

Trong NoSQL schema linh hoạt:

~~~javascript
{ _id: "a" }
{ _id: "b", description: null }
{ _id: "c", description: "" }
{ _id: "d", description: "Mô tả hợp lệ" }
~~~

Chúng có thể đại diện các trạng thái khác nhau:

- **Missing:** không có field, ví dụ document schema cũ hoặc chưa biết thông tin.
- **Null:** field hiện diện với giá trị null theo quy định.
- **Empty:** chuỗi/mảng tồn tại nhưng không chứa phần tử.
- **Giá trị bình thường:** có nội dung hợp lệ.

MongoDB có semantics cần nhớ:

~~~javascript
// Equality với null có thể khớp cả field null và field thiếu.
db.products.find({ description: null });

// Chỉ thiếu field.
db.products.find({ description: { $exists: false } });

// Field tồn tại, kể cả null.
db.products.find({ description: { $exists: true } });

// Field có BSON type null.
db.products.find({ description: { $type: "null" } });
~~~

Hợp đồng field cần ghi **required**, **nullable**, default và hành vi reader cũ khi thiếu. Một Boolean `isPublished: false` không luôn tương đương thiếu `isPublished`; thiếu field có thể nghĩa là trạng thái chưa được biết hoặc schema cũ chưa có field đó.

## 12. Mảng cần hợp đồng chi tiết hơn `array`

Một array cần nêu:

- Item type: string, number hay object?
- Có chấp nhận null item không?
- Thứ tự phần tử có ý nghĩa không?
- Có cho phép phần tử trùng không?
- Kích thước tối đa?
- Mảng rỗng có hợp lệ không?
- Có cần sửa, phân trang hay query từng phần tử độc lập không?
- Ai sở hữu các phần tử và vòng đời của chúng?

Ví dụ:

~~~javascript
{
  tags: ["keyboard", "mechanical"],
  workflowSteps: [
    { stepId: "s1", position: 1, name: "Chuẩn bị" },
    { stepId: "s2", position: 2, name: "Kiểm tra" }
  ]
}
~~~

Nếu thứ tự `workflowSteps` quan trọng, hợp đồng cần xác định `position` có được trùng không và cách di chuyển bước. Nếu mỗi step có identity ổn định, `stepId` phù hợp hơn việc dựa vào vị trí mảng khi update.

Mảng tăng không giới hạn dễ làm document lớn và tạo hot document. Trong trường hợp review, event hoặc log tăng liên tục, có thể cần collection riêng với reference thay vì nhúng tất cả vào Product.

## 13. Enum và state machine

Ví dụ `status` có các giá trị:

~~~text
DRAFT
ACTIVE
ARCHIVED
~~~

Hợp đồng không nên chỉ ghi “string”. Nó cần nói:

- Các mã hợp lệ và ý nghĩa của từng mã.
- Trạng thái mặc định khi tạo.
- Các chuyển trạng thái được phép.
- Ai có quyền chuyển.
- Nếu reader cũ gặp mã mới như `SUSPENDED`, ứng xử thế nào?
- Có cần timestamp và audit khi chuyển không?

Không dùng nhãn giao diện đã dịch như `"Đang bán"` làm enum nếu dữ liệu cần được nhiều ngôn ngữ/consumer xử lý theo mã ổn định.

Nếu nhiều boolean như `isActive` và `isArchived` biểu diễn các trạng thái loại trừ nhau, có thể xuất hiện tổ hợp mâu thuẫn. Một enum rõ ràng thường dễ quản lý hơn, trừ khi các cờ thực sự độc lập.

## 14. Data dictionary: bảng hợp đồng cho Product

| Field | BSON type | Required | Null? | Ngữ nghĩa và quy tắc |
|---|---|---|---|---|
| `_id` | string | Có | Không | ID kỹ thuật toàn cục, bất biến |
| `tenantId` | string | Có | Không | Tenant sở hữu; phải kiểm tra quyền |
| `sku` | string | Có | Không | Mã hiển thị, có thể đổi theo nghiệp vụ |
| `skuKey` | string | Có | Không | Khóa chuẩn hóa, unique theo tenant |
| `name` | string | Có | Không | Tên hiện hành, giới hạn độ dài |
| `status` | enum string | Có | Không | DRAFT, ACTIVE, ARCHIVED |
| `price.amountMinor` | long | Có | Không | Số tiền minor units, không âm |
| `price.currency` | string | Có | Không | Mã currency theo chính sách |
| `tags` | string array | Không | Không theo contract | Nhãn; reader legacy có thể mặc định [] |
| `dimensions.widthMm` | int | Không | Không theo contract | Chiều rộng, milimét |
| `createdAt` | date | Có | Không | Server cấp khi tạo |
| `updatedAt` | date | Có | Không | Server cập nhật khi ghi |
| `schemaVersion` | int | Có | Không | Version cấu trúc lưu trữ |

Ngoài bảng, cần ghi các bất biến không mô tả trọn bằng type:

- `skuKey` phải là kết quả chuẩn hóa của `sku`.
- `tenantId` lấy từ ngữ cảnh đã xác thực và được phép.
- `createdAt` không tự ý đổi sau khi tạo.
- `status` chuyển theo state machine.
- `price.currency` và `amountMinor` có một cặp giá trị hợp lệ.
- Khi ARCHIVED, SKU có được tái sử dụng hay không.
- Data retention, security classification và mọi consumer liên quan.

## 15. Một tài liệu hợp đồng dạng YAML

~~~yaml
contract:
  name: ProductDocument
  version: 2
  owner: CatalogService
  storage:
    engine: MongoDB
    collection: products
  identity:
    field: _id
    bsonType: string
    scope: global
    immutable: true
  tenancy:
    field: tenantId
    source: authenticatedContext
  businessKey:
    fields: [tenantId, skuKey]
    unique: true
    normalization: "trim + uppercase ASCII SKU v1"
    reuseAfterArchive: false
  fields:
    _id: { type: string, required: true, nullable: false }
    tenantId: { type: string, required: true, nullable: false }
    sku: { type: string, required: true, nullable: false }
    skuKey: { type: string, required: true, nullable: false }
    name: { type: string, required: true, nullable: false }
    status:
      type: string
      required: true
      enum: [DRAFT, ACTIVE, ARCHIVED]
    price:
      type: object
      required: true
      children:
        amountMinor: { type: int64, required: true, minimum: 0 }
        currency: { type: string, required: true }
    tags:
      type: "string[]"
      required: false
      defaultForLegacyRead: []
    createdAt: { type: datetime-utc, required: true, immutable: true }
    updatedAt: { type: datetime-utc, required: true }
    schemaVersion: { type: int32, required: true }
  consumers:
    - ProductDetailApi
    - SearchProjection
    - PricingPipeline
~~~

Đây là **mẫu tài liệu**, không phải YAML mà MongoDB tự động thực thi. Cần triển khai bằng validator, indexes, DTO, domain logic, query mapping và migration.

## 16. Bảo vệ cấu trúc bằng MongoDB `$jsonSchema`

Một validator MongoDB có thể kiểm tra field bắt buộc, type và một số ràng buộc cơ bản. Ví dụ tạo collection mới:

~~~javascript
db.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "sku", "skuKey",
        "name", "status", "price",
        "createdAt", "updatedAt", "schemaVersion"
      ],
      properties: {
        _id: {
          bsonType: "string",
          minLength: 1
        },
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        sku: {
          bsonType: "string",
          minLength: 1
        },
        skuKey: {
          bsonType: "string",
          pattern: "^[A-Z0-9-]{1,40}$"
        },
        name: {
          bsonType: "string",
          minLength: 1,
          maxLength: 200
        },
        status: {
          enum: ["DRAFT", "ACTIVE", "ARCHIVED"]
        },
        price: {
          bsonType: "object",
          required: ["amountMinor", "currency"],
          properties: {
            amountMinor: {
              bsonType: "long",
              minimum: 0
            },
            currency: {
              bsonType: "string",
              pattern: "^[A-Z]{3}$"
            }
          }
        },
        tags: {
          bsonType: "array",
          items: { bsonType: "string" }
        },
        createdAt: {
          bsonType: "date"
        },
        updatedAt: {
          bsonType: "date"
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 1
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Ví dụ giả định `_id` là string, `price.amountMinor` là BSON Int64, `schemaVersion` là BSON Int32. Khi dùng kiểu khác hoặc thiếu field bắt buộc, validator có thể từ chối ghi theo thiết lập.

### Giới hạn của validator

Validator bảo vệ nhiều phần của **schema cấu trúc**, nhưng không tự bảo đảm:

- SKU unique đúng phạm vi và an toàn đồng thời.
- `skuKey` chính là giá trị được chuẩn hóa từ `sku`.
- `tenantId` thuộc người dùng đang được ủy quyền.
- Trạng thái được chuyển theo business state machine.
- Hai cập nhật đồng thời không gây lost update.
- Vòng đời xóa/khôi phục và lịch sử nghiệp vụ.
- Hợp đồng của API, event và mọi consumer.

Không nên xem database validator là toàn bộ hợp đồng. Với collection legacy, phải kiểm kê dữ liệu trước khi siết validator để tránh ghi thất bại không dự kiến.

## 17. Unique index và concurrency

Đối với SKU không được tái sử dụng trong cùng tenant, có thể tạo:

~~~javascript
db.products.createIndex(
  { tenantId: 1, skuKey: 1 },
  {
    unique: true,
    name: "uq_products_tenant_sku"
  }
);
~~~

Unique index là hàng rào chống hai request đồng thời cùng insert SKU đã được cấp. Một query kiểm tra trước insert **không đủ**, vì hai request có thể cùng nhìn thấy “chưa tồn tại”.

~~~text
Request A: tìm SKU -> chưa có
Request B: tìm SKU -> chưa có
Request A: insert -> thành công
Request B: insert -> duplicate-key error
~~~

Service phải xử lý duplicate-key thành lỗi nghiệp vụ, ví dụ HTTP 409, không để lộ chi tiết nội bộ không cần thiết.

**Lưu ý:** trong MongoDB sharded collection, unique index có giới hạn theo shard key và cấu hình. Không thể hứa unique tùy ý trên toàn cluster chỉ vì lệnh hoạt động ở collection chưa sharded.

Index này áp trên mọi Product, kể cả ARCHIVED. Nếu business muốn cho tái sử dụng SKU sau archive, phải định nghĩa vòng đời và có thể dùng một index theo điều kiện khác, kèm quy tắc restore xung đột. Không đổi scope unique mà không sửa contract.

## 18. API contract không phải bản sao nguyên xi của BSON

Storage document:

~~~javascript
{
  _id: "prod_01J9QK7M8X6V2N3P4R5T6W7Y8Z",
  tenantId: "shop-17",
  skuKey: "KB-RED",
  price: {
    amountMinor: NumberLong("350000"),
    currency: "VND"
  },
  schemaVersion: 2
}
~~~

API response có thể là:

~~~json
{
  "id": "prod_01J9QK7M8X6V2N3P4R5T6W7Y8Z",
  "sku": "kb-red",
  "name": "Bàn phím cơ màu đỏ",
  "status": "ACTIVE",
  "price": {
    "amountMinor": 350000,
    "currency": "VND"
  }
}
~~~

API không nhất thiết trả `skuKey`, `schemaVersion` hoặc `tenantId` vì đó có thể là chi tiết nội bộ. Cần ghi mapping rõ:

| Storage | API | Quy tắc |
|---|---|---|
| `_id` string | `id` string | Không đổi identity |
| BSON `long` | JSON integer hoặc string | Tuân theo miền giá trị của client |
| BSON Date | ISO 8601 string | Có timezone |
| `skuKey` | Không xuất | Thuộc chuẩn hóa nội bộ |
| `tenantId` | Có thể không xuất | Scope vẫn được server kiểm tra |
| `schemaVersion` | Không bắt buộc xuất | Khác API version |

Không expose toàn bộ NoSQL document chỉ vì nó có hình dạng gần JSON. API là một boundary với security, compatibility và ngữ nghĩa riêng.

## 19. Java/Spring: DTO validation ở ranh giới API

Một request DTO Java:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;

public record CreateProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @Valid PriceRequest price,
    List<@NotBlank String> tags
) {}

record PriceRequest(
    @NotNull @PositiveOrZero Long amountMinor,
    @NotBlank @Pattern(regexp = "[A-Z]{3}") String currency
) {}
~~~

Đây là phần kiểm tra đầu vào. Server còn phải:

1. Lấy tenant từ ngữ cảnh xác thực.
2. Chuẩn hóa `skuKey` bằng chính sách thống nhất.
3. Sinh `_id` theo kiểu đã chọn.
4. Xác thực business invariants và trạng thái hợp lệ.
5. Ghi đúng BSON type, timestamp và schemaVersion.
6. Bắt lỗi duplicate-key trong tình huống concurrent insert.
7. Xử lý retry/idempotency nếu hợp đồng API yêu cầu.

Một job import hoặc consumer có thể bỏ qua controller, nên cần validation tại domain/service và database chứ không chỉ Jakarta Bean Validation.

### Mapping ID

Một class Spring Data MongoDB có thể có:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import java.time.Instant;

@Document("products")
public class ProductDocument {
    @Id
    private String id;

    private String tenantId;
    private String sku;
    private String skuKey;
    private String name;
    private String status;
    private Instant createdAt;
    private Instant updatedAt;
    private Integer schemaVersion;

    // Constructor, getters/setters và price value object
    // được bổ sung theo implementation.
}
~~~

Đây là **khung mapping**, chưa phải class hoàn chỉnh. Cần kiểm soát quy tắc chuyển giá trị Java sang BSON, đặc biệt `Long`, enum, ObjectId/string và nested value object.

## 20. Field ownership và quyền ghi

Một tài liệu hợp đồng nên ghi ai có quyền thay đổi từng field:

| Field | Owner | Đường thay đổi |
|---|---|---|
| `name` | Catalog | UpdateProductName |
| `sku`/`skuKey` | Catalog | ChangeSku với normalization + uniqueness |
| `status` | Product domain | Chuyển trạng thái hợp lệ |
| `price` | Pricing/Catalog theo kiến trúc | ChangePrice với currency |
| `tenantId` | Tenancy | Tạo/chuyển owner theo workflow |
| `createdAt` | Persistence/domain | Chỉ khi tạo |
| `updatedAt` | Persistence/domain | Khi ghi thành công |
| `schemaVersion` | Migration/writer | Theo cấu trúc lưu |

Search projection có thể chứa bản sao `name` nhưng không nên sửa Product nguồn. Nếu Product bị archive, search index có thể trễ; đường ghi giao dịch quan trọng phải xác nhận trạng thái có thẩm quyền chứ không chỉ tin projection.

## 21. Không đánh đồng các loại version

| Field | Ý nghĩa |
|---|---|
| `schemaVersion` | Cấu trúc document hiện thuộc version nào? |
| `aggregateVersion` | Thứ tự thay đổi trạng thái, có thể dùng chống lost update |
| `eventSchemaVersion` | Format payload event |
| `apiVersion` | Hợp đồng API với client |
| `normalizationPolicyVersion` | Quy tắc chuẩn hóa business key |
| `embeddingModelVersion` | Model tạo vector nếu có |

`schemaVersion = 2` không giúp chống việc hai request cùng đọc Product rồi ghi đè nhau. Muốn optimistic concurrency, dùng điều kiện version của trạng thái:

~~~javascript
db.products.updateOne(
  {
    _id: "prod_01J9QK7M8X6V2N3P4R5T6W7Y8Z",
    aggregateVersion: NumberLong("17")
  },
  {
    $set: { name: "Bàn phím cơ phiên bản mới" },
    $inc: { aggregateVersion: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
);
~~~

Nếu `matchedCount = 0`, dữ liệu có thể đã đổi hoặc bản ghi không còn. Ứng dụng cần phân biệt và xử lý conflict, không xem đó là ghi thành công.

## 22. Thêm field mới không nên phá reader cũ

Giả sử Product v1 thiếu `tags`, v2 muốn có `tags: []`.

Trình tự triển khai:

1. Định nghĩa ý nghĩa của mảng, item type và nullability.
2. Reader mới hiểu document thiếu `tags` theo chính sách tương thích.
3. Writer mới bắt đầu ghi `tags` nhất quán.
4. Backfill dữ liệu v1 nếu cần.
5. Đo tỷ lệ document thiếu field.
6. Chỉ sau khi các writer/consumer phù hợp, cân nhắc validator required.
7. Loại fallback legacy theo kế hoạch.

Một field optional không bảo đảm tương thích nếu reader cũ dùng strict parser hoặc xử lý không đúng unknown fields.

### Backward và forward compatibility

- **Backward:** reader mới đọc được dữ liệu do writer cũ tạo.
- **Forward:** reader cũ đọc được dữ liệu do writer mới tạo.
- **Full:** cả hai hướng trong phạm vi cam kết.

Cần kiểm tra thực tế qua consumer contract tests, không suy đoán từ chữ “optional”.

## 23. Rename field là migration nhiều bước

V1:

~~~javascript
{
  priceMinor: NumberLong("350000")
}
~~~

V2:

~~~javascript
{
  price: {
    amountMinor: NumberLong("350000"),
    currency: "VND"
  }
}
~~~

Một tiến trình chuyển đổi an toàn thường:

~~~mermaid
flowchart TD
    A["Reader hỗ trợ v1 và v2"] --> B["Writer mới ghi v2"]
    B --> C["Backfill document v1"]
    C --> D["Đối soát giá trị và version"]
    D --> E["Ngừng writer cũ"]
    E --> F["Siết validator"]
    F --> G["Bỏ fallback v1"]
~~~

Nếu tạm thời dual-write cả `priceMinor` và `price.amountMinor`, phải có một nguồn quyết định và ghi chúng trong cùng phạm vi nguyên tử phù hợp. Không để hai code path cập nhật độc lập khiến giá trị lệch.

Nếu V1 không có currency, migration phải biết currency mặc định **đúng theo nghiệp vụ**; không thể tự áp dụng một mã tiền cho dữ liệu đa tiền tệ.

## 24. Đổi kiểu string thành number: rủi ro âm thầm

Ví dụ dữ liệu legacy:

~~~javascript
{
  price: {
    amountMinor: "350000",
    currency: "VND"
  }
}
~~~

Dữ liệu mới:

~~~javascript
{
  price: {
    amountMinor: NumberLong("350000"),
    currency: "VND"
  }
}
~~~

String và numeric không có cùng semantics so sánh/index. Không nên cho rằng query theo number sẽ tự hoạt động đúng với mọi giá trị string cũ.

Migration cần:

- Kiểm kê số document theo BSON type.
- Phát hiện string không hợp lệ, số âm, overflow hoặc giá trị có dấu phân tách.
- Chuyển đổi chính xác, có checkpoint và khả năng resume.
- Đối soát số lượng và giá trị trước/sau.
- Chuyển mọi writer sang kiểu mới.
- Siết validator và bỏ đường đọc legacy khi an toàn.

Đổi tên field mà giữ sai **đơn vị** đôi khi còn nguy hiểm hơn đổi kiểu, vì validator có thể không phát hiện.

## 25. Enum mới cần kế hoạch consumer compatibility

V1 có `DRAFT`, `ACTIVE`, `ARCHIVED`. V2 thêm `SUSPENDED`.

Reader cũ có thể:

- Ném lỗi khi gặp enum lạ.
- Bỏ qua trạng thái mới.
- Mặc định sai thành `ACTIVE`.
- Hiển thị nhãn không xác định nhưng vẫn xử lý được.

Trước khi writer dùng `SUSPENDED`, cần xác định policy cho consumer cũ, nhất là với quyền truy cập, thanh toán và trạng thái giao dịch. Trong ngữ cảnh nhạy cảm, unknown enum có thể cần **fail closed** thay vì giả định cho phép.

## 26. Event contract có version riêng

Ví dụ event:

~~~json
{
  "eventId": "evt-1201",
  "eventType": "ProductRenamed",
  "eventSchemaVersion": 1,
  "aggregateId": "prod_01J9QK7M8X6V2N3P4R5T6W7Y8Z",
  "tenantId": "shop-17",
  "occurredAt": "2026-11-14T08:05:00Z",
  "aggregateVersion": 18,
  "data": {
    "oldName": "Bàn phím cơ màu đỏ",
    "newName": "Bàn phím cơ đỏ bản mới"
  }
}
~~~

Hợp đồng event phải quy định source, identity, phạm vi tenant, type, timestamp, schema version, thứ tự, duplicate, replay và retention.

Document `schemaVersion: 2` **không yêu cầu** event phải mang `eventSchemaVersion: 2`. Hai format có vòng đời thay đổi khác nhau, dù diễn đạt cùng dữ liệu nghiệp vụ.

## 27. Schema migration ảnh hưởng nhiều nơi hơn collection

~~~mermaid
flowchart TD
    A["Field contract thay đổi"] --> B["Document + validator"]
    A --> C["Indexes + queries"]
    A --> D["Java model + mapper"]
    A --> E["HTTP API"]
    A --> F["Events + CDC"]
    A --> G["ETL + báo cáo"]
    A --> H["Cache + read model"]
    A --> I["Backfill + monitoring"]
~~~

Nếu chỉ sửa Java class mà không cập nhật MongoDB index/query hoặc một dashboard dùng field cũ, kết quả có thể sai âm thầm.

Bản ghi quyết định migration nên có:

- Chủ sở hữu thay đổi.
- Danh sách producer/consumer chịu ảnh hưởng.
- Tương thích với version cũ.
- Thứ tự triển khai.
- Mốc backfill, đối soát và deprecation.
- Điều kiện rollback.
- Các metric chứng minh còn writer/reader legacy hay không.

## 28. Kiểm kê dữ liệu cũ trước khi bật validation chặt

Một collection có thể chứa đồng thời:

~~~javascript
{ priceMinor: 350000 }
{ price: { amountMinor: "350000", currency: "VND" } }
{ price: { amountMinor: NumberLong("350000"), currency: "VND" } }
{ price: null }
{ /* thiếu price */ }
~~~

Trước khi tạo validator chặt hoặc unique index, cần đo tình trạng:

1. Bao nhiêu document theo từng `schemaVersion`?
2. Những field nào thiếu hoặc có BSON type khác hợp đồng?
3. Business key nào trùng sau normalization?
4. Có dữ liệu nào không thể tự động chuyển đổi?
5. Có writer cũ vẫn ghi định dạng cũ không?
6. Có index và query nào đang phụ thuộc field cũ?
7. Backfill có thể chạy lại mà không nhân đôi thay đổi không?
8. Có cách kiểm tra dữ liệu sau migration không?

Không nên cho rằng việc tạo validator sẽ sửa dữ liệu legacy. Nó chỉ định nghĩa hành vi kiểm tra ghi theo cấu hình; remediation và migration vẫn cần thực hiện rõ.

## 29. Kiểm tra hợp đồng bằng test

| Nhóm kiểm tra | Tình huống |
|---|---|
| Identity | Hai representation ID không bị trộn ObjectId/string |
| Serialization | Java Long ghi BSON long |
| API mapping | `_id` được trả thành `id` đúng contract |
| Required/nullable | Thiếu name, name null, name rỗng được xử lý đúng |
| Unique scope | Hai tenant cùng SKU hợp lệ; một tenant trùng bị chặn |
| Concurrency | Hai insert cùng SKU không cùng thành công |
| Normalization | `" kb-red "` và `"KB-RED"` thành cùng key |
| Numeric | Không làm tròn sai số nguyên lớn |
| Date | Round-trip thời điểm UTC |
| Enum | Reader xử lý unknown status theo policy |
| Migration | Reader đọc được schema cũ đã cam kết |
| Security | API tenant A không đọc hoặc sửa được tenant B |
| Event | Consumer chịu được duplicate và out-of-order nếu hợp đồng yêu cầu |

Một test tạo xung đột SKU nên chạy ở môi trường thử nghiệm, không ghi dữ liệu cố tình trùng vào production.

### Không chỉ test happy path

Có thể cần thêm dữ liệu giả cho:

- Field literal có dấu chấm/dollar không mong muốn.
- Null trong mảng hoặc object con.
- Timestamp thiếu múi giờ khi parse.
- Currency không hỗ trợ.
- Document có dữ liệu lớn, mảng quá dài.
- Client gửi field server-owned như `tenantId` hoặc `schemaVersion`.
- Version cũ chưa migration hoặc ghi sau cutover.

## 30. Quyền riêng tư và retention cũng thuộc hợp đồng field

Ví dụ:

~~~yaml
field: customer.email
owner: IdentityService
purpose: "Thông tin liên hệ theo chính sách sản phẩm"
classification: personal-data
allowedWriters:
  - IdentityService
allowedReaders:
  - AuthorizedProfileApi
  - NotificationService
copyPolicy: "Không copy sang public search card"
retention: "Theo chính sách đã phê duyệt"
deletion: "Theo workflow xóa hoặc ẩn dữ liệu áp dụng"
~~~

Dữ liệu nhạy cảm bị duplicate vào cache, event hoặc read model sẽ làm tăng số nơi cần kiểm soát. Nên tối thiểu hóa trường được lưu, xác định người sở hữu và quy trình xóa/ẩn theo yêu cầu thực tế.

Không nhúng email, số giấy tờ hay thông tin cá nhân vào public ID nếu không có lý do được cân nhắc kỹ.

## 31. Tên field động và query security

Nếu cho client truyền bất kỳ tên field hoặc operator nào để tạo MongoDB query, ứng dụng có thể thực thi truy vấn không dự kiến hoặc truy cập đường dẫn nội bộ.

Nên dùng allowlist mapping:

~~~text
API sort field      -> MongoDB field
name                -> name
createdAt           -> createdAt
price               -> price.amountMinor
~~~

Chỉ cho phép những filter, operator và sort đã định nghĩa trong API contract. `tenantId` phải đến từ ngữ cảnh được xác thực và ủy quyền, không từ một query parameter mà client có thể giả mạo.

Một ID khó đoán hoặc một schema validator không thay thế kiểm tra quyền.

## 32. Khi nào cần giữ hai schema cùng lúc?

Có thể có mobile app chưa cập nhật, consumer event theo lịch triển khai khác, job import dùng writer cũ hoặc dữ liệu lịch sử chưa backfill.

Một chiến lược chuyển đổi có thể chọn:

- **On-read adapter:** reader đọc v1 và v2 rồi map thành domain model chung.
- **Eager migration:** backfill toàn bộ v1 trước khi siết.
- **Lazy migration:** chuyển v1 sang v2 khi ghi lại hoặc đọc theo policy.
- **Dual-read/dual-write:** trong thời gian ngắn, cần một source rõ và đối soát.
- **Projection rebuild:** tái dựng read model từ nguồn sau khi đổi schema.

Mỗi lựa chọn cần có thời hạn và tiêu chí dừng. Nếu reader hỗ trợ v1 mãi mãi mà không theo dõi, hệ thống sẽ tích lũy code phức tạp và dữ liệu khó quản lý.

## 33. Bài tập thực hành

### Bài A — ID trông giống nhau

Collection có một document với `_id` ObjectId và một document với `_id` string cùng 24 ký tự hex.

**Câu hỏi:** Query bằng một string có lấy cả hai document không?

**Gợi ý:** không. BSON ObjectId và string khác kiểu. Contract phải chọn một kiểu, migration phải xử lý ID và reference cũ.

### Bài B — SKU đa tenant

Hai shop cùng muốn mã `KB-RED`. Một developer tạo unique index chỉ trên `skuKey`.

**Câu hỏi:** Index đúng không?

**Gợi ý:** không nếu uniqueness chỉ áp dụng trong tenant. Cần index `(tenantId, skuKey)` và rule normalization. Chú ý hạn chế khi sharding.

### Bài C — Thời gian chờ

Một phiên bản lưu `timeout = 30` nghĩa là giây; phiên bản mới hiểu là mili giây.

**Câu hỏi:** Vì sao đây là thay đổi nguy hiểm dù type vẫn là number?

**Gợi ý:** field đổi ngữ nghĩa mà validator không tự nhận ra. Nên có tên rõ đơn vị như `timeoutMs` và migration có conversion/compatibility.

### Bài D — Thiếu tags

Document v1 không có `tags`, reader v2 đòi list bắt buộc.

**Câu hỏi:** Cần triển khai theo thứ tự nào?

**Gợi ý:** reader hỗ trợ missing theo chính sách, writer mới ghi đúng, backfill, quan sát legacy và cuối cùng siết validator.

### Bài E — Null và missing

Query `{ deletedAt: null }` có thể trả document thiếu `deletedAt` không?

**Gợi ý:** có. Cần phân biệt `$exists` và `$type` nếu nghiệp vụ yêu cầu field thực sự hiện diện với BSON null.

### Bài F — Schema version và concurrent write

Hai request cùng đọc Product có `schemaVersion = 2` và cùng sửa tên.

**Câu hỏi:** schemaVersion có ngăn lost update không?

**Gợi ý:** không. Cần aggregateVersion/version check hoặc cơ chế cập nhật có điều kiện phù hợp.

### Bài G — Enum mới

Writer mới bắt đầu ghi `SUSPENDED`, reader cũ chỉ hiểu DRAFT, ACTIVE, ARCHIVED.

**Câu hỏi:** Cần chuẩn bị gì?

**Gợi ý:** contract consumer, fallback an toàn, chính sách unknown enum, test và thứ tự triển khai. Trạng thái bảo mật không nên mặc định ACTIVE.

### Bài H — Giá lịch sử

Product hiện tại có giá 500.000, OrderLine cũ đã chốt giá 350.000.

**Câu hỏi:** Có nên sửa OrderLine theo Product.price?

**Gợi ý:** không nếu `unitPriceMinor` là giá tại thời điểm mua. Snapshot nghiệp vụ khác bản sao cache/projection cần đồng bộ.

## 34. Quy trình chuẩn hóa hợp đồng NoSQL cho một collection mới

1. **Xác định thực thể:** Document đại diện cho cái gì và thuộc aggregate nào?
2. **Xác định owner:** Ai có quyền tạo/sửa/xóa, field nào do server cấp?
3. **Thiết kế identity:** Kiểu ID, phạm vi unique, bất biến và representation công khai.
4. **Thiết kế business key:** Namespace, normalization, uniqueness và tái sử dụng.
5. **Chọn naming convention:** Collection, field, unit suffix, timestamp và enum.
6. **Viết schema:** BSON type, required, nullability, default, array/object và giới hạn.
7. **Ghi ngữ nghĩa:** Đơn vị, trạng thái, vòng đời, quyền, sensitivity và retention.
8. **Đặt các bảo vệ:** DTO validation, domain logic, database validator, unique/conditional constraints.
9. **Định nghĩa mappings:** Storage, API JSON, event và read model.
10. **Chọn index:** Query shape, shard key, chi phí ghi và unique scope.
11. **Lập kế hoạch tiến hóa:** schemaVersion, migration, compatibility, deprecation và rollback.
12. **Gắn test và monitoring:** Schema mismatch, duplicate key, legacy ratio, consumer errors và tiến độ migration.

Một hợp đồng tốt không chỉ là tập ví dụ JSON đúng định dạng. Nó nói rõ **mỗi giá trị có nghĩa gì, ai được thay đổi, dữ liệu có thể được đọc ra sao và làm sao giữ được tính đúng đắn qua nhiều phiên bản**.

## 35. Các sai lầm cần tránh

**“NoSQL linh hoạt nên không cần schema.”** Schema vẫn tồn tại dưới dạng kỳ vọng của code, query, index và consumer.

**“Tên field chỉ là vấn đề thẩm mỹ.”** Tên field là query path, cấu trúc index, mapping và một phần ngữ nghĩa nghiệp vụ.

**“Có `_id` là đủ unique mọi khóa.”** SKU, external ID và idempotency key có phạm vi riêng.

**“ObjectId và string giống nhau khi in ra.”** Kiểu BSON vẫn khác và ảnh hưởng query.

**“Giá là number nên không cần ghi unit.”** Currency, minor unit và quy tắc làm tròn là một phần hợp đồng.

**“Missing, null và empty giống nhau.”** Có thể cho kết quả query và ý nghĩa nghiệp vụ khác nhau.

**“Validator giải quyết mọi bất biến.”** Authorization, concurrency, state machine và uniqueness cần thêm cơ chế phù hợp.

**“Đổi tên biến Java là đủ để rename field.”** Collection, index, ETL, event và API consumer có thể vẫn đọc tên cũ.

**“SchemaVersion giúp chống lost update.”** Nó nói về cấu trúc, khác aggregateVersion.

**“Thêm field optional luôn tương thích.”** Consumer strict và serializer có thể không hỗ trợ.

**“Migration chạy xong không lỗi là thành công.”** Cần đối soát, phát hiện writer cũ và đo dữ liệu legacy còn lại.

**“ID ngẫu nhiên đã đủ bảo mật.”** Quyền truy cập và tenant isolation phải được kiểm tra độc lập.

## 36. Kết luận

**Quy ước định danh** cho biết một thực thể được nhận diện ổn định như thế nào và các khóa nghiệp vụ có phạm vi duy nhất ở đâu. **Quy ước tên trường** giúp mọi producer/consumer hiểu đúng kiểu, đơn vị, thời gian, nullability và ý nghĩa của dữ liệu. **Tài liệu hóa hợp đồng** liên kết những lựa chọn đó với owner, validation, API, index, migration và kiểm thử.

Schema linh hoạt là một khả năng của NoSQL, còn **hợp đồng dữ liệu được thiết kế và thực thi nhất quán mới là nền tảng để hệ thống phát triển lâu dài**. Khi từng field có ý nghĩa rõ, ID có quy tắc ổn định và thay đổi được triển khai theo chiến lược tương thích, nhóm có thể tận dụng sự linh hoạt mà không phải đánh đổi tính đúng đắn của dữ liệu.
