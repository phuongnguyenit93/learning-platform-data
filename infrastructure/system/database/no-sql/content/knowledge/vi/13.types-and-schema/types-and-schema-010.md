# Thêm trường, đổi kiểu và duy trì nhiều phiên bản ứng dụng trong NoSQL

Cơ sở dữ liệu NoSQL thường cho phép các document hoặc item trong cùng collection/bảng không có tập trường giống nhau. Một bản ghi cũ có thể chỉ chứa `name`; bản ghi mới có thêm `preferredLanguage`; trong giai đoạn chuyển đổi có thể tồn tại cả `fullName` và `displayName`. Sự linh hoạt này không đồng nghĩa hệ thống **không có schema**: các kỳ vọng về tên trường, kiểu dữ liệu và ý nghĩa của chúng vẫn nằm trong mã nguồn, API, chỉ mục, validator, sự kiện và cache.

Khi người dùng đang truy cập hệ thống liên tục, chúng ta không thể dừng tất cả dịch vụ, sửa mọi bản ghi rồi khởi động đúng một phiên bản ứng dụng mới. Trong quá trình **rolling deployment**, API V1, API V2, worker cũ, consumer mới và những ứng dụng mobile chưa cập nhật có thể cùng đọc/ghi dữ liệu. Một thay đổi tưởng đơn giản như đổi `totalPrice` từ chuỗi sang số có thể làm reader cũ crash, khiến writer cũ ghi đè field mới, hoặc tạo kết quả lọc/sắp xếp sai.

Mục tiêu của bài học thuộc chương **Kiểu dữ liệu và schema** là thiết kế quá trình thay đổi schema có thể triển khai dần, bảo vệ dữ liệu, có quan sát và có đường phục hồi. Ví dụ dùng MongoDB, Java và một số cơ chế của Redis, DynamoDB, Cassandra và công cụ tìm kiếm; các tính năng/giới hạn cần được kiểm chứng trên **sản phẩm, phiên bản, edition và topology thực tế**.

## 1. Schema vẫn tồn tại trong NoSQL

Schema là hợp đồng về **hình dạng, kiểu và ý nghĩa dữ liệu**. Một số hệ NoSQL không bắt buộc mọi record có cùng cấu trúc, nhưng ứng dụng vẫn cần hiểu chúng.

| Tầng | Schema xuất hiện ở đâu? | Ví dụ rủi ro khi thay đổi |
|---|---|---|
| Record | Field, kiểu dữ liệu, nested object, array | `price` là string hay decimal? |
| Index | Key pattern, sort/collation, type, projection | Index cũ không tối ưu query field mới |
| Validation | JSON Schema, validator database/app | Writer cũ bị từ chối khi field mới bắt buộc |
| Mô hình Java | DTO, entity, serializer/deserializer | Parse lỗi khi field thiếu hoặc sai kiểu |
| HTTP API | OpenAPI, JSON response, yêu cầu client | App mobile cũ không hiểu response mới |
| Event | Protobuf/Avro/JSON và version | Consumer cũ không đọc được event mới |
| Search/vector | Mapping, analyzer, embedding dimension/model | Phải rebuild/reindex |
| Cache | Key namespace, serialized value, TTL | V1 lấy phải value theo V2 |

Có ba loại thay đổi thường gặp:

- **Additive:** thêm trường optional không làm thay nghĩa field cũ.
- **Transformative:** đổi tên, đổi kiểu hoặc thay cấu trúc nested/array.
- **Destructive:** xóa field, xóa hỗ trợ định dạng cũ, đổi ý nghĩa một field có tên không đổi.

Thay đổi additive có thể đơn giản hơn nhưng **không mặc định luôn tương thích**, nhất là khi reader strict hoặc writer cũ replace nguyên document.

## 2. Ví dụ xuyên suốt: nâng cấp document đơn hàng

V1 lưu một Order:

~~~json
{
  "_id": "ord-1001",
  "customerId": "u42",
  "status": "CREATED",
  "totalPrice": "19.99",
  "currency": "USD",
  "createdAt": "2026-11-14T08:00:00Z"
}
~~~

Đội sản phẩm muốn:

1. V2 thêm `preferredLanguage` để gửi email theo ngôn ngữ; nếu legacy record thiếu, ứng dụng cần fallback.
2. V3 thay `totalPrice` dạng chuỗi thập phân bằng `totalPriceMinor` dạng số nguyên ở đơn vị nhỏ nhất.
3. V3 lưu thời gian kiểu native date thay vì chuỗi ISO.
4. V1 và V2 có thể đồng thời chạy một khoảng thời gian.

Một document **đang trong giai đoạn chuyển tiếp** có thể là:

~~~javascript
{
  _id: "ord-1001",
  customerId: "u42",
  status: "CREATED",
  totalPrice: "19.99",          // giữ cho V1
  totalPriceMinor: NumberLong("1999"),
  currency: "USD",
  createdAt: "2026-11-14T08:00:00Z",
  createdAtDate: ISODate("2026-11-14T08:00:00Z"),
  preferredLanguage: "vi",
  schemaVersion: 3
}
~~~

Đây **không phải định dạng cuối cùng bắt buộc**. Nó là một cách duy trì tương thích trong thời gian chuyển đổi. Nếu V1 vẫn cần `totalPrice` và `createdAt` cũ, xóa chúng ngay sẽ làm V1 lỗi. Ngược lại, giữ cả hai mãi mãi cũng gây chi phí, khả năng lệch dữ liệu và khó xác định nguồn chuẩn.

## 3. Ma trận tương thích reader–writer

Khi nói một schema “backward compatible”, phải ghi rõ đang xét reader, writer, API hay event. Những câu hỏi chính:

| Tình huống | Câu hỏi |
|---|---|
| Reader V2 đọc document V1 | Có xử lý field thiếu, null và kiểu cũ không? |
| Reader V1 đọc document V2 | Có bỏ qua unknown field hay từ chối parse? |
| Writer V1 sửa document V2 | Có xóa field mới khi replace toàn bộ document? |
| Writer V2 sửa document V1 | Có chuyển kiểu và tạo field mới đúng không? |
| Consumer V1 đọc event V2 | Có còn hiểu payload và bảo toàn nghiệp vụ? |
| Reader V3 đọc backup V1 | Có thể upcast dữ liệu lịch sử không? |

Một deployment nhiều phiên bản tạo ma trận:

~~~text
                      Data V1      Data V2       Data V3
Reader V1               OK        phải thử       có thể lỗi
Reader V2            fallback        OK          phải thử
Reader V3            upcast        upcast           OK

Writer V1 -> record V3:
  replaceOne có thể xóa field mới
  update một field cũ có thể bảo tồn field mới
  nhưng có thể vẫn gây mâu thuẫn giữa hai format
~~~

**Tương thích chiều đọc không chứng minh tương thích chiều ghi**. Đây là nguyên nhân phổ biến khiến dữ liệu mới “tự biến mất” sau một lần cập nhật từ worker cũ.

## 4. Missing, explicit null và default có ý nghĩa khác nhau

Giả sử V2 thêm `preferredLanguage`:

~~~json
{"_id":"ord-1"}
{"_id":"ord-2","preferredLanguage":null}
{"_id":"ord-3","preferredLanguage":""}
{"_id":"ord-4","preferredLanguage":"vi"}
~~~

Các trạng thái:

- **Missing:** record được tạo trước khi có field hoặc writer không ghi.
- **Null:** giá trị được gán null rõ ràng; có thể là “chưa biết” hay “đã bị xóa”.
- **Empty string:** đã có field nhưng có thể không hợp lệ.
- **String hợp lệ:** mã ngôn ngữ có ý nghĩa nghiệp vụ.

MongoDB có thể giúp phân loại:

~~~javascript
// Không có field.
db.orders.find({
  preferredLanguage: { $exists: false }
});

// Field có giá trị null đúng kiểu BSON null.
db.orders.find({
  preferredLanguage: { $type: "null" }
});

// Field lưu string.
db.orders.find({
  preferredLanguage: { $type: "string" }
});
~~~

Predicate ngắn `{preferredLanguage: null}` có thể khớp cả missing và null trong MongoDB. Vì vậy, migration cần phân biệt hai loại phải dùng điều kiện tường minh.

**Default ở runtime** (khi thiếu thì đọc thành `vi`) không đồng nghĩa với **backfill ghi `vi` vào mọi record cũ**. Backfill có thể thay đổi thông tin được lưu vĩnh viễn; nếu sau này quy tắc fallback đổi hoặc ngôn ngữ tùy theo khách, quyết định đó có tác động.

## 5. Thêm field theo nguyên tắc optional trước, required sau

Quy trình triển khai nên bắt đầu từ reader:

1. Cho V2 reader đọc được record V1 thiếu `preferredLanguage`.
2. Đặt quy tắc fallback rõ ràng: dùng cấu hình của khách hay mặc định hệ thống?
3. Deploy reader mới trước khi đòi writer cũ ghi field mới.
4. Writer mới bắt đầu lưu `preferredLanguage` theo một kiểu thống nhất.
5. Backfill record cũ nếu cần chuyển field từ optional thành required.
6. Đo số record thiếu, sai kiểu, null bất thường; không chỉ đếm tổng document.
7. Chỉ siết validator khi mọi writer cũ đã được thay và dữ liệu đã được đối soát.

Ví dụ:

~~~javascript
// V2 cập nhật từng field, bảo tồn các field mà nó không sửa.
db.orders.updateOne(
  { _id: "ord-1001" },
  {
    $set: {
      status: "PAID",
      preferredLanguage: "vi"
    }
  }
);
~~~

Ngược lại, dùng `replaceOne` với một đối tượng V1 chỉ chứa các field cũ có thể làm mất `preferredLanguage` đang lưu trong document.

### 5.1. Có nên backfill ngay mọi record?

Không nhất thiết. Nếu phần lớn record cũ hiếm đọc và fallback runtime rẻ, có thể triển khai reader mới trước và backfill theo lô sau. Nếu cần index/query hoặc validator `required` theo field mới, có thể phải backfill toàn bộ. Quyết định phụ thuộc nhu cầu truy vấn, số lượng record, chi phí ghi và thời điểm phải hoàn tất.

## 6. schemaVersion: nhãn định dạng chứ không phải phép màu

Một số hệ thêm field `schemaVersion`:

~~~json
{
  "_id": "ord-2001",
  "schemaVersion": 3,
  "totalPriceMinor": 1999,
  "currency": "USD",
  "preferredLanguage": "vi"
}
~~~

Nó có thể giúp reader chọn adapter/upcaster, biết hợp đồng nào áp dụng và lập thống kê về dữ liệu legacy. Nhưng:

- Document V1 có thể không có `schemaVersion`.
- Writer cũ vẫn có thể làm mất field mới khi replace.
- Một document ghi version 3 chưa chắc có toàn bộ field nếu migration lỗi.
- Version record không đồng nghĩa version ứng dụng.
- Khi hai team thêm field độc lập, version tuyến tính toàn hệ có thể khó điều phối.

Với thay đổi thêm field đơn giản, feature detection có thể đủ. Với thay đổi phá kiểu hoặc cấu trúc khó nhận biết, version tường minh thường có ích. **Version phải phản ánh định dạng thực, không chỉ là nhãn được gán khi deploy.**

## 7. Đổi tên field: dual-read trước khi xóa field cũ

Giả sử V1 dùng `fullName`, V2 muốn `displayName`. Nếu thực hiện ngay:

~~~javascript
db.users.updateMany({}, {
  $rename: { fullName: "displayName" }
});
~~~

reader V1 vẫn tìm `fullName` và sẽ thấy missing. V1 writer có thể tiếp tục ghi field cũ, làm document xuất hiện cả hai dạng.

Một reader chuyển tiếp:

~~~javascript
function readDisplayName(doc) {
  if (typeof doc.displayName === "string" &&
      doc.displayName.length > 0) {
    return doc.displayName;
  }

  if (typeof doc.fullName === "string" &&
      doc.fullName.length > 0) {
    return doc.fullName;
  }

  return null;
}
~~~

Writer mới có thể tạm ghi cả hai:

~~~javascript
db.users.updateOne(
  { _id: "u42" },
  {
    $set: {
      fullName: "Nguyen Mai",
      displayName: "Nguyen Mai"
    }
  }
);
~~~

Nhưng **dual-write không tự bảo đảm hai field luôn nhất quán**. V1 writer có thể cập nhật `fullName` mà không cập nhật `displayName`. Phải có một nguồn có thẩm quyền, quy tắc phiên bản/điều phối hoặc tạm dừng đường ghi legacy cho field này.

Backfill khi trường mới còn thiếu:

~~~javascript
db.users.updateMany(
  {
    displayName: { $exists: false },
    fullName: { $type: "string" }
  },
  [
    { $set: { displayName: "$fullName" } }
  ]
);
~~~

Đây là pipeline update để lấy giá trị từ `fullName`. Với collection lớn, phải chia lô có kiểm soát, không mặc định quét/ghi toàn bộ vào giờ cao điểm.

### 7.1. Mismatch cần quy tắc rõ

~~~json
{"fullName":"Old Name","displayName":"New Name"}
~~~

Không thể chỉ “chọn field mới” nếu cập nhật mới nhất đến từ writer cũ và chưa được đồng bộ sang field mới. Các lựa chọn: một command handler có thẩm quyền, optimistic concurrency, tạm cấm writer cũ sửa field, hoặc đối soát theo version/timestamp đáng tin cậy. Mọi cách cần được kiểm tra với update đồng thời.

## 8. Đổi kiểu: không thay cùng tên field khi reader cũ còn tồn tại

V1:

~~~json
{"totalPrice":"19.99","currency":"USD"}
~~~

V3:

~~~json
{"totalPriceMinor":1999,"currency":"USD"}
~~~

Nếu thay `totalPrice` trực tiếp thành số `1999`, reader V1 mong string dollar có thể lỗi hoặc hiểu 1999 USD thay vì 19.99 USD. Một tên field cũ không nên mang hai ý nghĩa không tương thích.

Đổi kiểu an toàn thường cần:

1. Field mới có tên thể hiện đơn vị, ví dụ `totalPriceMinor`.
2. Reader mới ưu tiên field mới, fallback chuyển field cũ.
3. Writer mới ghi field canon và duy trì field cũ tạm thời nếu reader V1 vẫn cần.
4. Backfill record cũ với converter được test.
5. Đối chiếu kết quả trên record thật, kể cả ngoại lệ.
6. Ngừng ghi field cũ, cuối cùng xóa nó sau khi reader/worker/consumer cũ đã hết.

Đổi kiểu dữ liệu là **đổi hợp đồng ý nghĩa**: có thể cần giữ precision, currency, khoảng giá trị, thời điểm áp dụng và quy tắc rounding.

## 9. Ví dụ chuyển tiền bằng Java với BigDecimal

Đối với giá tiền, đừng dùng `Double.parseDouble` rồi nhân 100 nếu yêu cầu chính xác số học thập phân. Đối với USD trong ví dụ, 19.99 dollar là 1999 cents. Với currency khác, phải tra quy tắc số đơn vị nhỏ nhất thay vì mặc định luôn có hai chữ số thập phân.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MoneyConverter {
    private MoneyConverter() {}

    public static long parseUsdToCents(String legacy) {
        if (legacy == null || legacy.isBlank()) {
            throw new IllegalArgumentException("Missing price");
        }

        BigDecimal dollars = new BigDecimal(legacy);
        BigDecimal cents = dollars.movePointRight(2)
            .setScale(0, RoundingMode.UNNECESSARY);

        return cents.longValueExact();
    }
}
~~~

Các trường hợp mong đợi:

~~~text
"19.99"    -> 1999
"0.01"     -> 1
"100.00"   -> 10000
"1.999"    -> lỗi: quá độ chính xác cho cents
"abc"      -> lỗi parse
null       -> lỗi thiếu giá trị
~~~

Nếu dữ liệu legacy từng cho phép `"19,99"`, `"$19.99"` hoặc dấu phân tách hàng nghìn, phải xác định rõ kiểu format và xử lý chúng riêng. Không thay tất cả dấu phẩy bằng dấu chấm rồi mặc định sẽ đúng; `"1,234"` có thể mang nhiều nghĩa theo locale.

Một backfill tốt phải có error queue cho record không convert được, không âm thầm đặt giá 0.

## 10. Đổi timestamp string thành kiểu Date

V1:

~~~json
{"createdAt":"2026-11-14T08:00:00Z"}
~~~

V2:

~~~javascript
{ createdAtDate: ISODate("2026-11-14T08:00:00Z") }
~~~

Lý do tách field là để không phá reader cũ và có thể xây index theo kiểu native date.

Cần xác minh:

- Chuỗi cũ có timezone hoặc offset không?
- Có định dạng giờ địa phương thiếu timezone không?
- Có timestamp không hợp lệ, giây nhuận hoặc độ chính xác khác không?
- Có query đang sort theo string và dựa vào cùng một định dạng ISO không?
- Khi cast sang Date, precision và timezone được giữ thế nào?
- Có trường hợp dữ liệu đến từ nhiều múi giờ hay không?

Nếu record là `"2026-11-14 08:00:00"` không kèm timezone, không thể đoán chắc đó là 08:00 UTC. Migration phải có quy tắc và có thể phân loại record cần xử lý.

## 11. Đổi cấu trúc nested object và array

V1 lưu:

~~~json
{
  "items": ["SKU-A", "SKU-B"]
}
~~~

V2 muốn:

~~~json
{
  "itemsV2": [
    {"sku":"SKU-A","quantity":1,"unitPriceMinor":1999},
    {"sku":"SKU-B","quantity":2,"unitPriceMinor":499}
  ]
}
~~~

Đây không chỉ là thay đổi JSON shape. Nó đòi hỏi câu trả lời:

- Một SKU xuất hiện trong array cũ có nghĩa quantity=1 hay không?
- Hai lần lặp SKU có phải quantity=2 không?
- Giá chốt tại thời điểm mua có ở nguồn lịch sử khác không?
- Nếu chỉ còn giá hiện tại, có được phép điền nó vào đơn cũ không?
- Client cũ còn ghi `items` và có làm mất `itemsV2` không?
- Các index `items` và `itemsV2.sku` đã được thay/đo chưa?

Nếu không đủ dữ liệu để khôi phục giá tại thời điểm mua, **không tự tạo dữ liệu có vẻ chính xác nhưng sai nghiệp vụ**. Cần để trạng thái unknown, ghi lỗi migration hoặc có quy trình quyết định riêng.

## 12. Expand → migrate → contract

Đây là phương pháp hữu ích khi phải triển khai không downtime:

~~~mermaid
flowchart TD
    A["EXPAND: schema và reader hiểu cũ/mới"] --> B["Writer mới ghi format mới trong chế độ tương thích"]
    B --> C["MIGRATE: backfill và đối soát"]
    C --> D{"Còn writer/reader cũ?"}
    D -->|Có| E["Duy trì compatibility, theo dõi mismatch"]
    E --> C
    D -->|Không| F["CONTRACT: bỏ field cũ, siết validator, dọn index"]
    F --> G["Giám sát và lưu khả năng phục hồi"]
~~~

### 12.1. Expand

- Deploy reader hỗ trợ cả V1 và V2.
- Thêm field mới dạng optional; validator vẫn chấp nhận record cũ.
- Writer mới ghi thêm field mới nhưng chưa xóa trường cũ khi còn consumer legacy.
- Tạo index mới trước khi đổi query, có kế hoạch đo chi phí build.
- Đặt metric cho fallback, invalid/missing fields và mismatch.

### 12.2. Migrate

- Chuyển record cũ thành định dạng mới bằng converter chuẩn.
- Chia batch, checkpoint, giới hạn throughput.
- Xử lý record lỗi/thiếu dữ liệu, không đoán giá trị.
- Đối chiếu dữ liệu cũ/mới, kiểm tra writer cũ không tạo thêm nợ schema.
- Ghi rõ tiến độ và phạm vi còn chưa chuyển.

### 12.3. Contract

- Xác định mọi writer/reader/consumer cũ đã ngừng hoặc có adapter.
- Dừng dual-write, dừng fallback nếu an toàn.
- Bật validator chặt hơn nếu cần.
- Xóa field/index cũ bằng migration riêng.
- Giám sát thời gian đủ dài và có quy trình sửa lỗi sau contract.

**Contract thường là điểm khó rollback nhất**: khi field cũ đã xóa, deploy lại V1 binary chưa chắc hoạt động.

## 13. Rolling deployment và nguy cơ writer cũ

Trong khi deploy V2, hệ có thể đồng thời có:

~~~text
API V1: đọc/ghi Order V1
API V2: đọc cả V1/V2, ghi thêm field mới
Worker V1: vẫn xử lý hoàn tiền theo class V1
Worker V2: xử lý theo schema mới
Consumer V1: còn lấy event V1
Mobile app cũ: có thể không cập nhật trong nhiều tuần
~~~

Vấn đề lớn không chỉ là old reader không hiểu new data. **Old writer có thể xóa dữ liệu mới khi replace document.**

~~~javascript
// Code V1 chỉ biết vài field cũ, không giữ totalPriceMinor.
db.orders.replaceOne(
  { _id: orderId },
  legacyOrderObject
);
~~~

Sau lệnh này, `totalPriceMinor` có thể biến mất. Khả năng khắc phục:

- Thay bằng field-level updates khi phù hợp.
- Cập nhật writer cũ để bảo tồn unknown fields trước khi bật V2 writes.
- Dùng conditional version/optimistic concurrency.
- Tạm chuyển mọi ghi qua command service tương thích.
- Chạy test V1 writer trên document V2 và đo field loss.

Nếu V1 worker quan trọng chưa được nâng cấp, kế hoạch rollout phải giải quyết nó trước. **V2 reader tolerant không cứu được khi V1 writer đang làm mất thông tin.**

## 14. Backfill dữ liệu lớn có checkpoint và idempotency

Một collection hàng chục triệu record không nên được cập nhật bừa trong giờ cao điểm. Backfill cần khả năng dừng, tiếp tục, chạy lại và cô lập lỗi.

Quy trình:

1. Chọn tập record cần chuyển bằng `$exists`, `$type` hoặc version.
2. Định nghĩa converter và error handling.
3. Duyệt theo khóa ổn định hoặc partition có checkpoint.
4. Đọc record hiện tại, convert và ghi **có điều kiện** khi vẫn là phiên bản mong đợi.
5. Giữ lại record lỗi trong error queue để xử lý sau, không bỏ qua vì cursor đã tiến.
6. Giới hạn batch, concurrency và rate; quan sát CPU, disk, replication lag.
7. Chạy lại nếu crash; cùng record không bị chuyển thành giá trị khác.
8. Kết thúc bằng đếm dữ liệu còn thiếu/sai kiểu và đối chiếu số tiền.

MongoDB giúp phân loại:

~~~javascript
db.orders.countDocuments({
  totalPriceMinor: { $exists: false }
});

db.orders.countDocuments({
  totalPrice: { $type: "string" }
});

db.orders.countDocuments({
  totalPriceMinor: { $type: "long" }
});
~~~

Số Long ở đây là hợp đồng chọn cho ví dụ, không phải kiểu duy nhất phù hợp với mọi hệ. Tùy business rule, có thể dùng Decimal128 hoặc một numeric type khác, nhưng **writer và reader phải thống nhất đơn vị**.

Giả mã backfill:

~~~text
checkpoint = loadCheckpoint("price-v3")

while true:
    docs = fetchRecordsAfter(checkpoint.lastId, batchSize=500)
    if docs.empty:
        break

    for doc in docs:
        if doc.totalPriceMinor already valid:
            continue

        result = strictConvert(doc.totalPrice, doc.currency)
        if result.failed:
            recordFailure(doc.id, reason)
            continue

        conditionalUpdate(
            id = doc.id,
            expectedVersion = doc.version,
            expectedLegacyPrice = doc.totalPrice,
            set = { totalPriceMinor: result.value }
        )

    saveCheckpoint(maxIdInBatch)
    throttleIfStorageBusy()
~~~

Checkpoint chỉ có ý nghĩa khi **record bị lỗi được lưu để retry** hoặc có một vòng kiểm tra còn thiếu cuối cùng. Một scan đi hết collection nhưng bỏ qua 2.000 record lỗi không phải migration hoàn tất.

### 14.1. Backfill trong lúc writer cũ vẫn đang chạy

Writer V1 có thể liên tục tạo thêm `totalPrice` mà không có `totalPriceMinor`. Nếu tốc độ sinh mới lớn hơn tốc độ backfill, nợ schema không giảm. Vì vậy cần đo:

- Tốc độ record mới được ghi theo schema cũ.
- Tốc độ backfill chuyển thành công.
- Số record thiếu field mới theo ngày/tenant.
- Số record bị V1 overwrite làm mất field mới.
- Thời gian còn lại trước khi đủ điều kiện contract.

Đừng kết luận xong chỉ vì batch hiện tại đã duyệt hết số record nhìn thấy lúc bắt đầu.

## 15. Validator: siết sau khi đã triển khai tương thích

MongoDB hỗ trợ schema validation. Trong giai đoạn expand, field mới có thể vẫn optional và validator chạy chế độ cảnh báo.

Ví dụ minh họa:

~~~javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        preferredLanguage: { bsonType: "string" },
        totalPriceMinor: { bsonType: "long" }
      }
    }
  },
  validationAction: "warn"
});
~~~

Ví dụ này **không được áp dụng máy móc** trên collection thật vì thay validator có thể làm mất các rule hiện có. Cần lấy và hợp nhất với chính sách validation hiện tại rồi thử trên môi trường staging.

Về sau, nếu tất cả writer hỗ trợ, có thể cân nhắc `required` và `validationAction: "error"`. Nhưng việc bắt field mới trước khi V1 writer ngừng hoạt động có thể làm V1 update/insert bị từ chối. Tính năng validation cũng cần hiểu cách ứng xử với legacy invalid documents và quyền bypass.

JSON Schema bảo vệ **hình dạng dữ liệu**, không tự bảo vệ mọi bất biến nghiệp vụ xuyên document như tổng giá dòng hàng đúng với Order.

## 16. Index và query phải đổi theo schema

V1 truy vấn khoảng giá trên field string:

~~~javascript
db.orders.createIndex({ totalPrice: 1 });
~~~

V3 muốn numeric range:

~~~javascript
db.orders.createIndex({ totalPriceMinor: 1 });
db.orders.find({
  totalPriceMinor: { $gte: NumberLong("2000") }
});
~~~

Một trường string như `"100"` và `"20"` có thứ tự lexicographic khác thứ tự số. Index string không tự trở thành index numeric, và việc trộn kiểu có thể khiến filter/sort trả sai tập dữ liệu so với ý nghĩa nghiệp vụ.

Cần:

1. Xác định query mới và key pattern theo điều kiện/sort.
2. Tạo index mới trước khi chuyển read traffic, đánh giá chi phí build.
3. Backfill đầy đủ phần dữ liệu sẽ được query.
4. Chạy explain/query plan trên dữ liệu trộn kiểu và sau migration.
5. Đo read p95/p99, write amplification, memory và disk I/O.
6. Chỉ xóa index cũ khi chắc chắn consumer legacy đã ngừng.

Cùng một trường tên cũ nhưng đổi kiểu trong search engine có thể **không được phép sửa mapping trực tiếp**; thường phải xây index mới và reindex.

## 17. Java: serializer tolerant và upcaster tập trung

Một DTO cũ có thể được cấu hình bỏ qua unknown fields:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public class OrderLegacyDto {
    public String id;
    public String customerId;
    public String totalPrice;
    public String status;
}
~~~

Điều này có thể giúp V1 reader không crash vì field V2 mới, nhưng không có tác dụng với trường bị đổi kiểu không tương thích hoặc V1 writer replace mất unknown fields.

Một adapter V3 đọc cả format cũ và mới:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Map;

public final class OrderAdapter {
    private OrderAdapter() {}

    public static long usdCents(Map<String, Object> data) {
        Object modern = data.get("totalPriceMinor");
        if (modern instanceof Long cents) {
            return cents;
        }

        Object legacy = data.get("totalPrice");
        if (legacy instanceof String text
            && "USD".equals(data.get("currency"))) {
            return new BigDecimal(text)
                .movePointRight(2)
                .setScale(0, RoundingMode.UNNECESSARY)
                .longValueExact();
        }

        throw new IllegalArgumentException("Unknown order price format");
    }
}
~~~

Adapter cần được kiểm thử về null, overflow, decimal scale và currency. Trong production, code cũng phải hiểu BSON int/long/decimal theo hợp đồng serializer đang dùng.

Phân biệt:

- **Read-time upcast:** chuyển record cũ trong bộ nhớ, không sửa DB.
- **Write-time normalization:** mọi ghi mới dùng format canonical.
- **Backfill:** chuyển record đã lưu.
- **Event upcast:** chuyển event lịch sử khi replay.

Không nên rải logic convert ở nhiều service vì các service có thể xử lý record lỗi theo cách khác nhau.

## 18. Redis/key–value: version namespace hoặc version value

Redis có thể lưu JSON dưới một key:

~~~redis
SET cache:order:v1:ord-1001 "{\"totalPrice\":\"19.99\",\"currency\":\"USD\"}" EX 300
~~~

Nếu ứng dụng mới lưu JSON dạng `totalPriceMinor` dưới cùng key, cache client cũ có thể parse sai. Một cách là dùng key namespace mới:

~~~text
cache:order:v1:ord-1001
cache:order:v2:ord-1001
~~~

Ưu điểm: mỗi client thấy format đúng với phiên bản nó hiểu. Đánh đổi: nhiều bản cache, cache miss khi đổi version, TTL và invalidation riêng. Khi Order thay đổi, logic cập nhật/xóa cache cần biết các version đang phục vụ; tránh dữ liệu V1 cũ tồn tại quá lâu.

Với Redis hash, thêm một field bằng `HSET` có thể không làm client `HGET` field cũ lỗi. Nhưng đổi ý nghĩa/kiểu một field hoặc dùng serializer strict với `HGETALL` vẫn cần kế hoạch tương thích.

## 19. DynamoDB và Cassandra: thay đổi key/schema khác document JSON

DynamoDB cho phép item khác nhau về thuộc tính, nhưng primary key và GSI vẫn quyết định đường truy vấn. Thêm attribute không tạo ra index hiệu quả tự động; thêm GSI có chi phí build, storage, write và consistency riêng.

Khi cần đổi key phân vùng/sort để phục vụ access pattern mới, thường phải thiết kế bảng/projection mới. Conditional updates có thể bảo vệ version khi V1/V2 writer cạnh tranh.

Cassandra/ScyllaDB định nghĩa cột và primary key rõ qua CQL:

~~~sql
ALTER TABLE customer_profiles
ADD preferred_language text;
~~~

Cú pháp này minh họa **thêm cột**, không điền giá trị cho hàng cũ. Reader mới vẫn phải xử lý missing/null. Không nên giả định có thể đổi primary key, clustering order hoặc kiểu mọi cột bằng một lệnh `ALTER` không rủi ro. Với thay đổi không tương thích, thêm cột/bảng mới, migrate theo partition và chuyển query là một chiến lược thường cần đánh giá.

Khi làm việc với Cassandra, cần tính cả tombstone, compaction, schema agreement và tác động của migration trên nhiều partition; không dùng full scan/`ALLOW FILTERING` tùy tiện trên production.

## 20. Search mapping và vector index

Trong Elasticsearch/OpenSearch hoặc công cụ tương tự, mapping field string thành numeric thường không thể sửa trực tiếp trên index đã có dữ liệu theo cách một bảng JSON linh hoạt. Một chiến lược là:

~~~text
catalog_v1 -> chứa price keyword
catalog_v2 -> mapping priceMinor numeric

1. Tạo catalog_v2 với mapping mới.
2. Reindex/backfill từ nguồn dữ liệu có thẩm quyền.
3. Đồng bộ những cập nhật phát sinh trong lúc build.
4. Chạy query kiểm tra filter, sort, relevance và p99.
5. Chuyển read alias có kiểm soát sang v2.
6. Giữ đường rollback phù hợp trước khi xóa v1.
~~~

Tính nguyên tử của alias switch, hoạt động của write alias và cách replay thay đổi phải được xác nhận theo phiên bản sản phẩm.

Với vector search, thay model embedding có thể khiến vector cũ/mới không còn so sánh hợp lệ, ngay cả khi số chiều bằng nhau. Cần quản lý model version, re-embed dữ liệu và chuyển traffic theo index/version, không trộn tự do.

## 21. Event schema: dữ liệu cũ vẫn còn trong queue và archive

Sau khi database đã chuyển V3, một consumer mới vẫn có thể phải replay event V1 từ Kafka, archive hoặc outbox.

V1:

~~~json
{
  "eventId": "evt-1001",
  "eventType": "OrderCreated",
  "eventVersion": 1,
  "orderId": "ord-1001",
  "totalPrice": "19.99"
}
~~~

V2:

~~~json
{
  "eventId": "evt-1002",
  "eventType": "OrderCreated",
  "eventVersion": 2,
  "orderId": "ord-1002",
  "totalPriceMinor": 1999,
  "currency": "USD"
}
~~~

Một consumer V1 chỉ hiểu `totalPrice` có thể thất bại khi nhận V2. Có thể:

- Tạm phát cả field cũ/mới trong giai đoạn cùng tồn tại.
- Dùng version event mới và adapter tương ứng.
- Áp dụng schema registry/compatibility tests cho các reader/writer.
- Giữ upcaster V1 sau khi live writer V1 đã ngừng để phục vụ replay.
- Nâng consumer trước khi dừng phát event V1.

Avro, Protobuf và JSON có quy tắc tương thích khác nhau. Với Protobuf, không tái sử dụng field number đã xóa; nên `reserved` số cũ. Với Avro, việc thêm field/default cần được thử theo chế độ compatibility cụ thể của registry; không suy rằng mọi thay đổi “additive” đều phù hợp mọi consumer.

### Event gửi lại và sai thứ tự

Nếu event V3 được consumer nhận trước event V2, projection không nên bị cập nhật lùi về dữ liệu cũ. Cần event ID, aggregate version hoặc nguồn thứ tự đáng tin, và idempotent consumer. Schema evolution không được làm mất các cơ chế này.

## 22. Đồng bộ projection và tránh dual-write xuyên hệ

Một kiến trúc có nguồn Order chuẩn và nhiều đường đọc:

~~~mermaid
flowchart TD
    A["Order Command API"] --> B["Orders: nguồn chuẩn"]
    B --> C["Outbox / CDC có thể replay"]
    C --> D["Search index"]
    C --> E["Cache V1/V2"]
    C --> F["Analytics"]
    C --> G["Notification consumer"]
~~~

Nếu ứng dụng ghi đồng thời trực tiếp vào database và search index, một thao tác có thể thành công còn thao tác khác thất bại. Khi schema đổi, rủi ro tăng: mapping, version và độ trễ đồng bộ có thể khác nhau.

Một hướng thiết kế là commit thay đổi ở nguồn chuẩn cùng outbox, rồi consumer cập nhật projection và có khả năng replay. Nhưng vẫn phải xử lý duplicate event, out-of-order, poison message, lag và backfill. Không có cơ chế đồng bộ nào tự thay thế việc xác định **độ mới dữ liệu được phép** ở từng API.

## 23. Rollback là bài toán dữ liệu, không chỉ là code

Một bảng các trạng thái:

| Giai đoạn | Có thể quay về V1 dễ dàng? | Vì sao |
|---|---|---|
| Chỉ thêm reader hiểu format mới | Thường dễ | Dữ liệu chưa đổi |
| Writer V2 thêm field optional, V1 bỏ qua | Có thể, cần test | V1 có thể replace và xóa field mới |
| Writer V2 đổi kiểu cùng tên field | Rủi ro cao | V1 parse/logic có thể hỏng |
| Đã dừng ghi field cũ | Không đơn giản | V1 reader có thể thiếu dữ liệu |
| Đã xóa field cũ/index cũ | Khó | Cần migration ngược hoặc roll forward |
| Event V2 đã vào queue/consumer | Code rollback chưa đủ | Consumer cũ vẫn có thể gặp payload mới |

Đánh dấu **điểm không thể rollback** trước deploy. Nếu conversion không thuận nghịch hoặc field cũ đã bị xóa, phương án sửa tiến (roll forward) có thể an toàn hơn chạy lại binary cũ.

Backup không giải quyết mọi thứ: restore toàn database về snapshot trước migration có thể làm mất Order mới phát sinh. Cần diễn tập restore, reconciliation hoặc migration sửa ngược có điều kiện.

## 24. Feature flag và canary theo nhóm

Một rollout có thể có các pha:

~~~text
Phase 1: 100% reader có thể đọc V1 + V2
Phase 2: 1% writer V2, theo dõi mismatch và lỗi
Phase 3: 5% -> 25% -> 100% writer V2
Phase 4: Backfill dữ liệu cũ theo batch
Phase 5: 100% reader ưu tiên field V2, dừng writer V1
Phase 6: Contract khi không còn consumer legacy
~~~

Flag có thể tắt đường ghi mới, nhưng **không tự hoàn tác dữ liệu đã migrate**. Cần đo canary:

- Tỷ lệ record missing/invalid theo schema mới.
- Fallback read count và parse errors.
- Mismatch field cũ/mới.
- Writer instance còn chạy version cũ.
- p50/p95/p99, error/timeout, write conflicts.
- DB CPU/I/O, replication lag, index build pressure.
- Consumer/event error và projection lag.

Nếu mismatch xuất hiện, cần dừng mở rộng rollout và xác định nguồn dữ liệu có thẩm quyền trước khi backfill tiếp.

## 25. Kiểm thử tương thích có hệ thống

Bộ test nên bao phủ cả dữ liệu và phiên bản:

| Test | Input hoặc tình huống | Kết quả cần xác nhận |
|---|---|---|
| V2 reader + V1 data | Thiếu field mới | Fallback đúng |
| V1 reader + V2 data | Có unknown field | Không crash nếu hợp đồng cho phép |
| V1 writer + V2 record | Cập nhật status | Không làm mất `totalPriceMinor` |
| Missing vs null | Một record mỗi loại | Không nhập nhằng |
| Đổi tiền chuẩn | `"19.99" USD` | `1999` cents |
| Đổi tiền lỗi | `"1.999"`, null, overflow | Báo lỗi, không âm thầm sửa |
| Rename conflict | `fullName` khác `displayName` | Quy tắc ưu tiên đúng |
| Concurrent writers | V1/V2 cùng update Order | Version/CAS ngăn mất update |
| Backfill restart | Crash giữa batch | Idempotent, không bỏ mất record lỗi |
| Replay event | Event V1 từ archive | V3 consumer đọc được |
| Index migration | Truy vấn giá ở V1/V2 | Kết quả/sort đúng |
| Rollback flag | Tắt V2 writer khi đã có V2 data | Reader còn hoạt động |
| Cross-tenant | Hai tenant có cùng business ID | Không trộn quyền/dữ liệu |
| Restore | Snapshot schema hỗn hợp | Có thể đọc và tiếp tục migrate |

Không nhất thiết chạy tất cả test trong production. Nhưng kết luận “tương thích” phải dựa trên các cặp reader–writer quan trọng, bao gồm worker nền, queue consumer và các batch job chạy không thường xuyên.

## 26. Bài tập: nâng cấp Order đang có nhiều phiên bản chạy đồng thời

**Bối cảnh giả định:** collection `orders` có 500.000 record legacy. Có API V1, API V2, worker thanh toán V1 và consumer email V1. V2 muốn thêm `preferredLanguage`; V3 muốn đổi chuỗi giá thành `totalPriceMinor` và timestamp native Date.

### A. Thiết kế

1. Viết document mẫu V1, V2 và V3 trong giai đoạn chuyển tiếp.
2. Liệt kê field bắt buộc, field optional và quy tắc missing/null của từng phiên bản.
3. Vẽ ma trận reader/writer V1–V3 và điểm không tương thích.
4. Xác định cách giá tiền được lưu canonical và currency fraction digits.
5. Viết điều kiện chính xác khi nào được xóa field legacy.

### B. Viết mã và migration

1. Viết reader Java fallback `preferredLanguage` và tiền legacy.
2. Viết conditional update thay vì replace whole document.
3. Viết MongoDB query đếm record thiếu field mới.
4. Thiết kế backfill theo batch có checkpoint/error queue.
5. So sánh record `totalPrice` và `totalPriceMinor` sau chuyển đổi.
6. Viết test xử lý invalid price, null và timestamp thiếu timezone.

### C. Thử rollout

1. Giả lập V1 writer và V2 writer cùng cập nhật Order.
2. Thử một V1 `replaceOne` trên V2 record; quan sát field loss.
3. Lên kế hoạch deployment reader → writer → backfill → contract.
4. Đề xuất flag/canary và metric dùng để dừng rollout.
5. Diễn tập rollback sau khi đã có V2 records; ghi rõ những giới hạn.
6. Thử replay một `OrderCreated V1` sau khi code V3 đã lên production.

### D. So sánh công nghệ

Giả sử thay MongoDB bằng DynamoDB hoặc Cassandra, hãy giải thích:

- Khả năng thay field/schema và key/index được giới hạn thế nào?
- Có cần thêm field/cột/bảng mới thay vì đổi kiểu tại chỗ không?
- Làm sao migrate theo partition/range mà không tạo scan không kiểm soát?
- Khi nào phải reindex hoặc xây projection mới?
- Conditional write/version giúp bảo vệ người ghi cũ và mới ra sao?

## 27. Các hiểu nhầm phổ biến

| Nhầm lẫn | Điều thực sự xảy ra | Hướng xử lý |
|---|---|---|
| “NoSQL không có schema” | Schema nằm ở code, API, index và dữ liệu | Quản lý hợp đồng/version |
| “Thêm field luôn an toàn” | Reader strict hoặc writer replace có thể lỗi | Test old reader/old writer |
| “Missing giống null” | Có thể khác nghĩa nghiệp vụ | Xác định predicate/default |
| “Thêm required trước rồi backfill” | V1 writer có thể bị từ chối | Optional → backfill → required |
| “Rename bằng một lệnh là xong” | V1 vẫn đọc/ghi field cũ | Dual-read/dual-write có thời hạn |
| “Ép float rồi nhân 100 cho giá tiền” | Mất precision hoặc nhầm format | Decimal và đơn vị tường minh |
| “Có schemaVersion là đủ” | Writer cũ vẫn có thể phá field mới | Test concurrency và record thực |
| “Rollback binary sẽ khôi phục dữ liệu” | Data/event đã đổi có thể không đọc được | Ranh giới rollback và repair |
| “Backfill chạy một lần là xong” | Crash, parse lỗi, writer cũ sinh dữ liệu | Checkpoint + error queue + đối soát |
| “Dual-write mãi mãi cho an toàn” | Tạo hai nguồn dữ liệu dễ lệch | Contract khi đủ điều kiện |
| “Index tự hiểu trường đã đổi kiểu” | Key type/mapping và query khác | Xây index mới, đo query |
| “Reader mới đọc được V1 là đủ” | V1 writer có thể làm mất field V2 | Kiểm tra cả chiều ghi |

## 28. Khi nào được ngừng hỗ trợ schema cũ?

Trước khi xóa `totalPrice` string hay `fullName` legacy, cần có bằng chứng:

1. Không còn API/worker/consumer cũ ghi định dạng cũ.
2. Client cũ có chính sách hỗ trợ rõ ràng, hoặc server vẫn cung cấp adapter riêng.
3. Dữ liệu legacy đã được backfill và xử lý các trường hợp lỗi.
4. Mismatch cũ/mới đã được đối soát; có người chịu trách nhiệm kết quả.
5. Query/index/validator/search/cache đã dùng format mới.
6. Replay/restore vẫn đọc được event và record lịch sử.
7. Đã xác định điều gì xảy ra nếu rollback sau contract.
8. Có metric cảnh báo field mới bị thiếu hoặc writer legacy xuất hiện trở lại.

Nếu chưa đáp ứng, duy trì tương thích tạm thời có thể rẻ hơn một migration làm hỏng dữ liệu nghiệp vụ.

## 29. Tổng kết

**Schema evolution trong NoSQL là một quá trình vận hành nhiều phiên bản**, không chỉ là việc thay một trường trong document. Với field mới, reader cần hiểu dữ liệu chưa có field; với field đổi kiểu/đổi tên, phải dùng định dạng chuyển tiếp và nguồn chuẩn rõ ràng; với dữ liệu lớn, cần backfill có checkpoint, idempotency và đối soát. Đồng thời phải xem xét writer cũ, index, event, cache, validation và rollback.

Trình tự cốt lõi là **expand → migrate → contract**: mở rộng khả năng đọc trước, triển khai writer mới có kiểm soát, chuyển dữ liệu legacy, đo hoàn tất rồi mới dọn format cũ. Một migration chỉ được coi là thành công khi **dữ liệu cũ và mới được đọc đúng, các phiên bản ứng dụng cùng tồn tại không làm mất thông tin, các bất biến nghiệp vụ không bị phá và hệ thống có đường phục hồi rõ ràng**.
