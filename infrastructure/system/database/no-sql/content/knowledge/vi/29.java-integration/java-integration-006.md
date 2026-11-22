# Ánh xạ định danh, số chính xác, ngày giờ và dữ liệu lồng nhau

## 1. Vì sao chỉ một kiểu dữ liệu bị ánh xạ sai có thể làm hỏng nghiệp vụ?

Giả sử một ứng dụng Java lưu đơn hàng vào NoSQL. Đối tượng Java có những thuộc tính:

~~~java
record Order(
    String orderId,
    BigDecimal totalAmount,
    Instant createdAt,
    ShippingAddress shippingAddress
) {}
~~~

Sau khi ghi và đọc lại, hệ thống gặp bốn vấn đề:

1. ID trong API là một chuỗi, nhưng trong MongoDB lại là ObjectId; tra cứu bằng chuỗi không tìm thấy bản ghi.
2. Tổng tiền là 999999999999.99, nhưng một tầng trung gian đổi sang double làm mất độ chính xác.
3. Ngày tạo đơn ở UTC được hiển thị như một ngày khác tại múi giờ người dùng.
4. Địa chỉ lồng nhau thiếu trường province; mapper tưởng không có địa chỉ và ghi đè toàn bộ object bằng null.

Đây không phải lỗi cú pháp Java. Đây là lỗi **hợp đồng ánh xạ dữ liệu** giữa các tầng:

~~~text
HTTP JSON
   |
   v
Java DTO / domain model
   |
   v
NoSQL driver / mapper / serializer
   |
   v
BSON / JSON / attribute values / CQL / bytes
   |
   v
Storage
~~~

Mỗi tầng có tập kiểu dữ liệu và quy tắc chuyển đổi riêng. Chương **Kết nối Java** của module **Database No SQL** yêu cầu người phát triển biết cách giữ nguyên ý nghĩa dữ liệu khi đi qua các tầng đó.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn và ánh xạ **định danh**: ObjectId, UUID, String, long, compound key và business key.
- Lưu **số chính xác**: BigDecimal, BSON Decimal128, số dạng chuỗi, tiền theo minor units và xử lý scale/rounding.
- Phân biệt **Instant, LocalDate, LocalDateTime, OffsetDateTime và ZonedDateTime**, chọn cách lưu ngày giờ có timezone, độ chính xác và quy tắc truy vấn.
- Ánh xạ **dữ liệu lồng nhau**: object, array, map, list, set, embedded document, UDT và JSON.
- Phân biệt **null, field vắng mặt, empty object, empty list** và giá trị mặc định.
- Viết code Java minh họa cho MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và Jackson mà không coi mọi driver có cùng kiểu dữ liệu.
- Đặt quy tắc schema evolution, validation, serialization, indexing và migration cho dữ liệu đang tồn tại.
- Kiểm tra round-trip, Unicode, timezone, số lớn, duplicate ID và các tình huống lỗi khó thấy.

## 2. Một mapping đúng phải bảo toàn ngữ nghĩa, không chỉ biên dịch được

### 2.1. Bảo toàn giá trị

Nếu Java có số 12345678901234567890.12, ghi rồi đọc lại phải trả đúng giá trị theo mức độ chính xác nghiệp vụ yêu cầu.

Nếu giữa đường chuyển số này thành Java double, khả năng số đọc về thay đổi là có thật.

### 2.2. Bảo toàn kiểu và đơn vị

Hai giá trị:

~~~text
Amount: 100
Currency: VND
~~~

và

~~~text
Amount: 100
Currency: USD
~~~

có cùng con số nhưng khác ý nghĩa. Kiểu BigDecimal chỉ giúp giữ số thập phân, không tự cho biết currency, đơn vị hay quy tắc làm tròn.

### 2.3. Bảo toàn ý nghĩa thời gian

Một timestamp có thể biểu diễn **một thời điểm tuyệt đối**; một giá trị ngày sinh chỉ là **ngày theo lịch**. Cả hai không nên chuyển thành một Java Date duy nhất rồi coi có cùng ý nghĩa.

### 2.4. Bảo toàn cấu trúc

JSON object lồng nhau:

~~~json
{
  "shipping": {
    "address": {
      "city": "Hà Nội",
      "postalCode": "100000"
    }
  }
}
~~~

khác với một string chứa nội dung JSON. Cách lưu quyết định khả năng query theo field, tạo index, partial update và validation.

### 2.5. Bảo toàn vòng đời schema

Document cũ có field missing, document mới có field null, và document khác có object trống. Nếu tất cả đọc thành cùng một giá trị mặc định, update lần sau có thể xóa mất thông tin.

### 2.6. Bảo toàn contract khi đổi driver

Một model có thể làm việc tốt với MongoDB POJO codec, nhưng không tự tương thích DynamoDB Enhanced Client hoặc Jackson chỉ vì cùng là Java record/class.

Mỗi serializer/driver cần kiểm chứng:

- Kiểu được hỗ trợ.
- Tên field và annotation.
- Chuyển đổi null/missing.
- Numeric range/precision.
- Timezone và time precision.
- Polymorphic/nested types.
- Cách khởi tạo record/class.

## 3. Bắt đầu từ hợp đồng kiểu dữ liệu của từng NoSQL

| Hệ | Định danh | Số và thập phân | Ngày giờ | Dữ liệu lồng nhau |
|---|---|---|---|---|
| MongoDB/BSON | ObjectId, String, binary UUID, số, document key | Int32, Int64, Double, Decimal128 | BSON DateTime là epoch milliseconds UTC | Embedded document, array |
| DynamoDB | PK/SK từ String/Number/Binary; ID theo quy ước app | Number biểu diễn dạng chuỗi thập phân theo giới hạn dịch vụ | Không có scalar native timestamp; thường String ISO hoặc epoch Number | Map, List, Set |
| Cassandra/ScyllaDB | uuid, timeuuid, text, bigint, compound primary key | int, bigint, varint, decimal, float, double | timestamp, date, time; một số kiểu khác tùy engine | collections, frozen values, UDT, tuple |
| Redis cơ bản | Byte/string key do app định nghĩa | String số + atomic integer commands, float semantics theo lệnh | Không có native universal timestamp type | String/Hash/List/Set/Sorted Set/Stream; JSON qua cách lưu/extension |
| JSON HTTP | Thường String ID | JSON number, có nguy cơ mất precision khi consumer dùng binary floating-point | Thường String ISO-8601 | Object, array, null |

### 3.1. Dữ liệu trên wire không giống kiểu Java

Ví dụ JSON:

~~~json
{
  "id": "507f1f77bcf86cd799439011",
  "amount": 123.45,
  "createdAt": "2026-11-14T08:30:00Z"
}
~~~

JSON không nói id là MongoDB ObjectId, amount phải dùng BigDecimal hay createdAt có nanosecond precision. **Schema/API contract** phải nói rõ.

### 3.2. Tránh “mọi thứ là String”

String dễ truyền giữa hệ, nhưng mất type-level validation và có thể làm sort/range query sai.

~~~text
"100" < "20" theo thứ tự chuỗi
100   > 20  theo thứ tự số
~~~

String thích hợp cho mã định danh, postal code và số phải giữ ký tự, nhưng số dùng tính toán/range cần có encoding và schema phù hợp.

### 3.3. Tránh “mọi thứ là Object”

Một Map<String,Object> tiện lưu JSON động nhưng có thể chuyển:

~~~text
123 -> Integer trên đường đọc A
123 -> Long trên đường đọc B
123 -> BigDecimal trên đường đọc C
~~~

Nếu phần nghiệp vụ cần kiểu xác định, dùng domain DTO/codec rõ ràng thay vì cast tự do.

## 4. Định danh có nhiều vai trò khác nhau

### 4.1. Technical ID

ID do database/ứng dụng sinh để định danh một record, ví dụ MongoDB ObjectId.

### 4.2. Business ID

ID có ý nghĩa nghiệp vụ:

~~~text
orderNumber = "ORD-2026-000123"
invoiceNumber = "INV-VN-2026-000345"
tenantId = "T17"
~~~

Business ID có format, namespace, uniqueness, vòng đời hoặc yêu cầu pháp lý riêng.

### 4.3. Idempotency key

Nhận diện một **ý định thao tác** để retry không tạo duplicate effect:

~~~text
operationId = "PAY-REQ-8d12"
~~~

Không tự dùng database row ID thay idempotency key nếu một logical command có thể tạo nhiều records hoặc kết quả chưa rõ khi timeout.

### 4.4. Partition/shard key

Quyết định data locality và khả năng query:

~~~text
PK = TENANT#T17
SK = ORDER#O101
~~~

Business ID có thể được dùng làm partition key hoặc chỉ là một field. Không mặc định mọi ID là shard key tốt: một tenant cực lớn có thể thành hot partition.

### 4.5. Correlation/trace ID

ID liên kết logs/traces của một request hoặc workflow không nhất thiết là business identity. Không dùng traceId để enforce unique order nếu mỗi retry tạo trace mới.

### 4.6. Một quy ước ID tốt

Hãy xác định:

- Namespace/tenant scope.
- Kiểu dữ liệu và encoding.
- Ai sinh ID, thời điểm sinh.
- ID có được phép đổi không.
- Unique trong một tenant hay toàn hệ.
- Có yêu cầu sort theo thời gian không.
- Có chứa PII hoặc thông tin cần che không.
- Có ổn định qua retry hay migration không.

## 5. MongoDB ObjectId và Java

MongoDB thường sử dụng BSON ObjectId làm trường _id, nhưng _id có thể dùng nhiều kiểu BSON khác; không bắt buộc mọi collection dùng ObjectId.

### 5.1. ObjectId không phải String

Document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  name: "An"
}
~~~

khác về kiểu với:

~~~javascript
{
  _id: "507f1f77bcf86cd799439011",
  name: "An"
}
~~~

Chuỗi hex trông giống ObjectId vẫn là String nếu được lưu như String.

### 5.2. Dùng MongoDB Java Driver ở mức Document

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.ObjectId;

ObjectId id = new ObjectId();
Document order = new Document("_id", id)
        .append("orderNumber", "ORD-2026-000123")
        .append("customerId", "U101");

MongoCollection<Document> collection = database.getCollection("orders");
collection.insertOne(order);

Document found = collection.find(
        new Document("_id", id)
).first();
~~~

Đoạn này giả định database đã được khởi tạo bằng MongoDB Java Driver.

### 5.3. Chuyển hex String tại boundary

~~~java
import org.bson.types.ObjectId;

public static ObjectId parseObjectId(String raw) {
    if (raw == null || !ObjectId.isValid(raw)) {
        throw new IllegalArgumentException("Invalid ObjectId");
    }
    return new ObjectId(raw);
}
~~~

Nếu API path nhận String thì cần parse/validate trước khi query ObjectId _id. Không viết query trực tiếp với raw String rồi tưởng driver tự ép kiểu trong mọi trường hợp.

### 5.4. ID tự sinh không nên lộ internals tùy tiện

ObjectId có cấu trúc chứa thành phần thời gian và random/counter. Có thể suy ra gần đúng thời gian tạo từ ObjectId, nhưng:

- Không phải timestamp nghiệp vụ đáng tin cho createdAt.
- Không bảo đảm thứ tự tuyệt đối của mọi write trên các máy.
- Không thay một source event sequence.
- Không nên xem khả năng khó đoán của ID là authorization.

Nếu cần thời điểm tạo chính xác, lưu createdAt riêng.

### 5.5. Kiểu _id phải nhất quán

Nếu migration làm collection trộn _id ObjectId và String, một logic GET by id có thể bỏ sót một phần records. Cần quyết định representation chính thức, adapter khi đọc legacy và kế hoạch chuyển đổi có kiểm chứng.

## 6. UUID: dùng String hay binary?

Java cung cấp:

~~~java
import java.util.UUID;

UUID customerId = UUID.randomUUID();
String apiValue = customerId.toString();
UUID restored = UUID.fromString(apiValue);
~~~

### 6.1. Ưu điểm

- Không đòi một global auto-increment counter.
- Dễ sinh ở application.
- Định danh cùng entity qua nhiều stores.
- Có biểu diễn chuỗi chuẩn phổ biến.

### 6.2. UUID version không tương đương

UUID v4 thường tạo từ ngẫu nhiên. Những phiên bản khác có encoding/semantics liên quan thời gian hoặc thứ tự. Không suy “mọi UUID đều sắp xếp theo thời gian” hay “UUID v4 cho createdAt”.

### 6.3. UUID trong MongoDB

MongoDB BSON có Binary UUID với subtype/representation khác nhau, trong đó các biểu diễn legacy có byte ordering khác chuẩn STANDARD.

Khi dùng Java UUID với MongoDB driver, cần chọn UUID representation rõ ràng phù hợp deployment, ví dụ STANDARD nếu thiết kế mới theo format thông dụng.

**Cảnh báo:** Một UUID nhìn cùng text nhưng được encode legacy và standard có thể không match cùng binary value. Migration từ legacy phải có kế hoạch chuyển/đọc tương thích, không chỉ đổi cấu hình driver.

### 6.4. UUID dưới dạng String

~~~json
{
  "customerId": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Lưu String có lợi cho giao tiếp đa hệ và debug, nhưng chiếm kích thước/chuẩn index khác Binary. Dữ liệu cùng collection phải có hợp đồng nhất quán.

### 6.5. UUID trong Cassandra

CQL cung cấp uuid và timeuuid; **timeuuid** có semantics thời gian theo UUID version phù hợp và thường dùng cho dữ liệu có thứ tự trong các thiết kế nhất định. UUID v4 không tự mang thứ tự thời gian.

Không lưu UUID string vào cột uuid mà không dùng kiểu binding của driver theo đúng schema.

## 7. ID dạng String và những mã cần giữ nguyên ký tự

### 7.1. Postal code, phone và customer code

~~~text
postalCode = "00120"
phone = "+84901234567"
customerCode = "0000001234567890"
~~~

Đây là **mã định danh**, không phải lượng để cộng trừ.

Nếu đổi thành long:

~~~text
"00120" -> 120
~~~

sẽ mất số 0 ở đầu.

### 7.2. Không dùng double cho ID số rất lớn

Một JavaScript consumer hoặc JSON parser dùng binary floating point có thể không biểu diễn chính xác mọi integer 64-bit. ID dài dạng số trong JSON có nguy cơ bị đổi trước khi tới Java.

Nếu ID chỉ có mục đích định danh, dùng String ở API contract thường an toàn hơn một JSON number cực lớn.

### 7.3. Canonicalization

Hai username:

~~~text
Alice
alice
~~~

có được xem là một? Cần business contract về case sensitivity, Unicode normalization và trimming. Không tự lowercase mọi ID kỹ thuật; ObjectId hex và UUID text có rules riêng, còn email/username cần xác định canonicalization theo domain.

### 7.4. Dấu phân cách trong compound key

Một key:

~~~text
TENANT#T17#ORDER#O101
~~~

chỉ có thể parse an toàn nếu thành phần không chứa dấu phân cách hoặc đã được escape/length-prefix theo contract.

### 7.5. Composite identity

Trong ứng dụng multi-tenant:

~~~text
(tenantId, orderId)
~~~

có thể là identity chuẩn. Một orderId chỉ unique trong tenant thì không được tra cứu/xóa bằng orderId một mình.

## 8. Auto-increment ID và hệ phân tán

### 8.1. Nút thắt sequence

~~~text
GLOBAL_ORDER_NUMBER = GLOBAL_ORDER_NUMBER + 1
~~~

Nếu mọi order cần một số tăng liên tục toàn hệ, bộ cấp sequence có thể là bottleneck và cần một điểm quyết định phối hợp.

### 8.2. Tách technical ID và display number

Có thể có:

~~~text
technicalId = UUID
invoiceNumber = INVOICE-2026-000045
~~~

Technical ID phục vụ partition/distributed writes; invoice number có quy tắc pháp lý/sequence riêng.

### 8.3. Không giả định gap-free

Nhiều cơ chế cấp sequence có khoảng trống vì rollback, crash hoặc reservation dải số. Nếu nghiệp vụ đòi số không được thiếu, phải làm rõ ràng buộc và workflow, không chọn UUID hay auto-increment một cách tùy tiện.

### 8.4. ID sinh tại server và retry

Nếu client POST tạo record không mang stable operationId, response timeout có thể khiến retry sinh một ID mới và tạo hai order. Idempotency key khác với việc server tạo unique _id.

## 9. Kiểu dữ liệu cho ID trong Java domain model

Một cách giảm nhầm lẫn:

~~~java
import java.util.UUID;

public record CustomerId(UUID value) {
    public CustomerId {
        if (value == null) {
            throw new IllegalArgumentException("customer ID required");
        }
    }
}

public record OrderNumber(String value) {
    public OrderNumber {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("order number required");
        }
    }
}
~~~

Khi model giữ CustomerId và OrderNumber là hai kiểu khác nhau, khó truyền nhầm chuỗi orderNumber vào hàm nhận customerId.

Tuy nhiên, driver/serializer không nhất thiết hỗ trợ các Java record wrapper này tự động. Cần custom codec/converter hoặc mapper rõ ràng tại persistence boundary.

## 10. Quyết định kiểu ID theo access pattern

| Câu hỏi | Gợi ý |
|---|---|
| ID là business code có leading zeros? | Lưu String |
| API cần độc lập với storage? | Dùng opaque ID trong API, map ở repository |
| MongoDB collection dùng ObjectId? | Parse String tại boundary, query ObjectId |
| Dữ liệu đa ngôn ngữ/đa store? | Chuẩn hóa UUID representation hoặc String contract |
| Cần global uniqueness? | Chọn generator/namespace phù hợp, kiểm chứng bằng key/constraint cần thiết |
| Cần thứ tự theo thời gian? | Dùng createdAt hoặc ID có ordering contract, không suy từ UUID v4 |
| Một tenant có nhiều orders? | Xem composite key (tenantId, orderId) |
| Retry tạo record? | Stable operationId/idempotency |
| Dữ liệu nhiều shard? | Tránh sequence/hot partition key nếu không cần |

**Chốt ý:** ID đúng không chỉ là chuỗi đẹp. Nó là một phần của uniqueness, lookup, partitioning, API compatibility và khả năng khôi phục khi retry.

## 11. Vì sao double không thích hợp làm số tiền chính xác?

### 11.1. Số thập phân và binary floating-point

Trong Java:

~~~java
double a = 0.1;
double b = 0.2;
System.out.println(a + b); // 0.30000000000000004
~~~

Nhiều phân số thập phân không có biểu diễn hữu hạn trong hệ nhị phân. Double có ích cho tính toán khoa học hoặc giá trị xấp xỉ, nhưng thường không phù hợp khi yêu cầu tổng tiền và đối soát đúng đến đơn vị nhỏ nhất.

### 11.2. BigDecimal

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);

System.out.println(sum.toPlainString()); // 0.3
~~~

BigDecimal biểu diễn giá trị thập phân với precision/scale rõ ràng. Nhưng sử dụng BigDecimal trong Java **chưa đủ** nếu serializer lưu nó dưới dạng double hoặc consumer ở ngôn ngữ khác parse JSON number thành floating-point.

### 11.3. Tránh tạo BigDecimal từ double đã bị xấp xỉ

~~~java
BigDecimal risky = new BigDecimal(0.1);
BigDecimal expected = new BigDecimal("0.1");
~~~

Giá trị risky biểu diễn chính xác binary floating-point value đang có, có thể là một dãy thập phân dài khác 0.1.

Sử dụng String từ nguồn thập phân đáng tin hoặc parser nhận numeric literal trực tiếp thành BigDecimal. BigDecimal.valueOf(double) có cách xây dựng khác constructor double nhưng không khôi phục được precision mà upstream đã làm mất.

### 11.4. BigDecimal không tự định nghĩa tiền tệ

Hai BigDecimal cùng bằng 100 có thể tương ứng 100 VND hoặc 100 USD. Cần lưu currency và cách diễn giải minor units/rounding.

## 12. Scale, precision và phép so sánh BigDecimal

### 12.1. Precision và scale

~~~text
BigDecimal "123.4500":
  precision = 7
  scale     = 4
  numeric value = 123.45
~~~

Precision là số chữ số có nghĩa của biểu diễn decimal; scale là số chữ số sau dấu thập phân theo biểu diễn Java.

### 12.2. equals khác compareTo

~~~java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));     // false
System.out.println(x.compareTo(y));  // 0
~~~

**equals** xem cả value và scale; **compareTo** so giá trị số. Nếu business rule cần numeric equality, sử dụng compareTo; nếu contract đòi scale cố định, validate scale riêng.

### 12.3. Khóa hash và BigDecimal

Hai giá trị x, y có compareTo bằng 0 nhưng equals khác có thể là hai keys khác nhau trong HashMap/HashSet. Không trộn semantics numeric equality với object equality mà không chuẩn hóa:

~~~java
BigDecimal canonical =
        amount.setScale(2, java.math.RoundingMode.UNNECESSARY);
~~~

RoundingMode.UNNECESSARY yêu cầu amount đã có thể biểu diễn chính xác ở scale 2; nếu không sẽ ném ArithmeticException. Đây là cách hữu ích để **từ chối** đầu vào có quá nhiều chữ số lẻ, không âm thầm làm tròn.

### 12.4. Phép chia cần quy tắc

~~~java
BigDecimal amount = new BigDecimal("10.00");
BigDecimal share = amount.divide(
        new BigDecimal("3"),
        2,
        java.math.RoundingMode.HALF_EVEN
);
~~~

Kết quả 3.33 theo ví dụ, nhưng ba phần 3.33 chỉ thành 9.99. Nếu phân bổ tiền, cần **chính sách phân phối số dư** cho phần còn lại, không chỉ phép chia đơn thuần.

### 12.5. MathContext khác scale

MathContext điều chỉnh precision và rounding cho phép tính; setScale điều chỉnh scale. Không dùng MathContext với precision quá thấp cho toàn bộ phép tính tiền rồi coi đó là bảo đảm giữ đủ chữ số.

## 13. Mô hình Money: amount và currency phải đi cùng nhau

Một value object Java:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        if (amount == null || currency == null) {
            throw new IllegalArgumentException("amount and currency required");
        }
        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException("unsupported currency fraction digits");
        }
        amount = amount.setScale(fractionDigits, RoundingMode.UNNECESSARY);
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
~~~

Đây là ví dụ value object đơn giản. Trong production:

- Fraction digits của ISO currency không luôn đủ để mô tả cash rounding, custom token hoặc quy tắc nhà cung cấp.
- Giá có thể cần scale khác số tiền settlement.
- Có trường hợp currency hoặc business rule đòi rounding đặc thù.
- Không cộng hai currencies bằng cách cộng số đơn thuần.

### 13.1. Lưu amount decimal

~~~json
{
  "amount": "123.45",
  "currency": "USD"
}
~~~

String decimal giúp tránh một số consumers làm tròn qua JSON number, nhưng muốn query/sort/aggregate theo số cần converter/schema/index phù hợp.

### 13.2. Lưu theo minor units

~~~json
{
  "amountMinor": 12345,
  "currency": "USD"
}
~~~

Nếu quy ước 1 USD = 100 minor units, amountMinor=12345 tương ứng 123.45 USD. Tuy nhiên không phải mọi currency có hai chữ số thập phân.

### 13.3. Chọn một mô hình chuẩn

Một service có thể chọn decimal ở source và minor units ở API, hoặc ngược lại. Điểm quan trọng là quy tắc chuyển đổi **có kiểm chứng**, không trộn amount, amountCent và amountMinor cùng tên một cách mơ hồ.

## 14. Lưu số tiền bằng long minor units

Java:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public static long toMinorUnits(BigDecimal amount, int scale) {
    BigDecimal scaled = amount
            .setScale(scale, RoundingMode.UNNECESSARY)
            .movePointRight(scale);
    return scaled.longValueExact();
}

public static BigDecimal fromMinorUnits(long minorUnits, int scale) {
    return BigDecimal.valueOf(minorUnits, scale);
}
~~~

### 14.1. Vì sao longValueExact?

~~~java
BigDecimal tooLarge = new BigDecimal("999999999999999999999");
~~~

Gọi longValue thông thường có thể cắt/đổi giá trị nếu vượt range. longValueExact ném lỗi khi không thể biểu diễn chính xác, giúp ứng dụng **từ chối overflow** thay vì âm thầm sai tiền.

### 14.2. Không hardcode scale=2

Một số đơn vị tiền hoặc tài sản kỹ thuật số có số chữ số lẻ khác nhau. Phải dựa trên currency/business contract và phiên bản của quy tắc, đặc biệt khi lưu dữ liệu lịch sử.

### 14.3. Tránh overflow khi cộng

~~~java
long total = Math.addExact(amountMinorA, amountMinorB);
~~~

Math.addExact kiểm tra overflow long. Nếu cần range lớn hơn, dùng BigInteger/BigDecimal theo contract của store và API.

### 14.4. Minor units với JSON

Nếu number vượt khoảng integer an toàn của JavaScript, client web có thể làm tròn khi parse JSON. Với số rất lớn, API có thể định nghĩa amountMinor là **chuỗi decimal integer**, sau đó chuyển thành BigInteger/long trong Java có kiểm tra range.

## 15. MongoDB Decimal128 và Java BigDecimal

MongoDB BSON có Decimal128 cho số thập phân chính xác trong phạm vi IEEE 754 decimal128. Decimal128 có giới hạn về precision và exponent; BigDecimal Java có thể biểu diễn những giá trị ngoài phạm vi này.

### 15.1. Ghi Decimal128

~~~java
import java.math.BigDecimal;
import org.bson.Document;
import org.bson.types.Decimal128;

BigDecimal amount = new BigDecimal("123456789012345.67");
Document payment = new Document("amount", new Decimal128(amount))
        .append("currency", "VND");
collection.insertOne(payment);
~~~

### 15.2. Đọc về BigDecimal

~~~java
Document stored = collection.find().first();
if (stored != null) {
    Decimal128 raw = stored.get("amount", Decimal128.class);
    BigDecimal restored = raw.bigDecimalValue();
}
~~~

### 15.3. Không ghi qua Double

Sai cho số tiền chính xác:

~~~java
Document bad = new Document("amount", 123456789012345.67d);
~~~

Đường ghi này lưu BSON Double, không phải Decimal128. Đọc lại vào BigDecimal sau đó không thể bảo đảm khôi phục decimal gốc.

### 15.4. Giới hạn Decimal128

Decimal128 hỗ trợ tối đa **34 chữ số có nghĩa** với dải exponent theo format decimal128. Một BigDecimal có hơn 34 chữ số có nghĩa hoặc exponent ngoài phạm vi có thể không chuyển chính xác/không được chấp nhận.

Kiểm tra conversion và validate range, không cứ BigDecimal là viết được thành Decimal128.

### 15.5. Decimal128 đặc biệt

Format Decimal128 có thể biểu diễn giá trị đặc biệt như NaN/Infinity. Những giá trị này không phải số tiền hợp lệ; domain validator cần loại bỏ nếu input từ nguồn không tin cậy.

### 15.6. Cẩn thận với schema cũ

Nếu một collection có:

~~~text
Old amount field: BSON Double
New amount field: BSON Decimal128
~~~

phải đọc/di chuyển dữ liệu legacy bằng một quy tắc có thể audit. Không silently cast double thành Decimal128 rồi tuyên bố dữ liệu lịch sử chính xác.

## 16. DynamoDB Number và Java BigDecimal

DynamoDB Number có biểu diễn ở dạng **chuỗi số thập phân** trong AttributeValue API. SDK Java có thể map tới BigDecimal/BigInteger trong phạm vi kiểu và giới hạn dịch vụ, thay vì buộc phải dùng double.

### 16.1. AWS SDK for Java v2, low-level AttributeValue

~~~java
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import java.math.BigDecimal;
import java.util.Map;

BigDecimal total = new BigDecimal("1234567890.12");

Map<String, AttributeValue> item = Map.of(
    "pk", AttributeValue.builder().s("ORDER#O101").build(),
    "total", AttributeValue.builder()
            .n(total.toPlainString()).build(),
    "currency", AttributeValue.builder().s("USD").build()
);
~~~

### 16.2. Đọc có kiểm tra

~~~java
AttributeValue raw = item.get("total");
BigDecimal restored = new BigDecimal(raw.n());
~~~

Không viết:

~~~java
double restored = Double.parseDouble(raw.n());
~~~

nếu nghiệp vụ yêu cầu chính xác thập phân.

### 16.3. Giới hạn precision/range

DynamoDB Number hỗ trợ tối đa **38 chữ số precision** và một dải exponent hữu hạn theo dịch vụ. Không phải BigDecimal vô hạn nào cũng lưu được.

Với số quá lớn, cân nhắc schema String hay chia thành các thành phần theo business contract, nhưng hiểu rõ hệ quả của sort/filter/aggregate.

### 16.4. Empty string và null

Trong SDK v2, một AttributeValue có thể mang S, N, BOOL, NULL, M, L, SS/NS/BS; phải phân biệt field không được gửi và field được gửi với NULL. Empty strings có semantics và giới hạn theo vai trò key/attribute; không tự dùng empty string làm partition key.

### 16.5. Enhanced Client

DynamoDB Enhanced Client có hỗ trợ mapping các Java bean/immutable models và converters. Nếu domain dùng BigDecimal, LocalDate hoặc nested value objects, cần chọn converter/schema phù hợp. Không tự suy tất cả Java types có native AttributeValue tương đương.

## 17. Cassandra/ScyllaDB: decimal, varint, int và bigint

CQL có nhiều kiểu số:

| CQL | Java thường dùng | Ghi chú |
|---|---|---|
| int | int / Integer | Signed 32-bit |
| bigint | long / Long | Signed 64-bit |
| varint | BigInteger | Arbitrary-precision integer theo kiểu; vẫn chịu giới hạn engine/tài nguyên |
| decimal | BigDecimal | Exact decimal |
| float | float / Float | Binary floating-point |
| double | double / Double | Binary floating-point |

### 17.1. CQL decimal

~~~sql
CREATE TABLE payments_by_id (
  tenant_id text,
  payment_id uuid,
  amount decimal,
  currency text,
  PRIMARY KEY ((tenant_id, payment_id))
);
~~~

Java driver minh họa:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

BigDecimal amount = new BigDecimal("120000.50");
UUID paymentId = UUID.randomUUID();

session.execute(
    session.prepare(
        "INSERT INTO payments_by_id " +
        "(tenant_id, payment_id, amount, currency) VALUES (?, ?, ?, ?)"
    ).bind("T17", paymentId, amount, "VND")
);
~~~

Đây là ví dụ trên một Java CQL driver cung cấp prepare/bind kiểu dữ liệu như mô tả; API cụ thể khác theo phiên bản driver.

### 17.2. Avoid lossy conversion

Nếu mapper lưu CQL decimal nhưng nhận Java double từ API, precision có thể đã mất trước khi bind. Chọn BigDecimal từ DTO/validator.

### 17.3. Số tiền và counter

Cassandra counter column có semantics và giới hạn riêng; không tự dùng counter cho số dư hoặc dữ kiện cần transaction mạnh. Decimal exact không tự giải quyết atomicity của nhiều updates.

### 17.4. Decimal equality/scale

Quy tắc CQL về encoding/sort/compare không nên được suy từ Java BigDecimal.equals. Domain cần quy ước scale, rounding và compare semantics khi xây unique business identifiers từ amount.

## 18. Redis: số dưới dạng string và giới hạn thao tác

Redis thông thường lưu String dưới dạng bytes, có lệnh số nguyên như INCRBY/DECRBY:

~~~text
INCRBY page:views 1
~~~

Những phép này có phạm vi signed 64-bit integer theo command.

### 18.1. Lưu tiền minor units

~~~text
SET invoice:O101:totalMinor 12345
SET invoice:O101:currency USD
~~~

Tuy nhiên, Redis có thực sự là nguồn chuẩn cho invoice hay chỉ cache phải được xác định riêng. Nếu Redis là cache, không dùng value này để tự quyết settlement.

### 18.2. Tránh floating increment cho tiền

Các phép tính float hoặc string-to-floating conversion không thích hợp làm cơ sở duy nhất cho money ledger cần exact decimal. Một key String lưu decimal như "123.45" không tự mang phép cộng decimal chính xác.

### 18.3. RedisJSON / hash mapping

Có thể lưu amount dưới dạng JSON string hay fields hash, nhưng serialization và scale phải do application định nghĩa. Redis Hash/JSON cũng không tự tạo domain Money type hoặc transaction xuyên payment provider.

### 18.4. Redis INCRBY và transaction safety

INCRBY nguyên tử ở phạm vi operation Redis được thực thi, nhưng retry cùng logical increment có thể làm tăng hai lần. Cần idempotency nếu không được phép duplicate effect.

## 19. JSON/Jackson và BigDecimal xuyên HTTP API

Một DTO:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record PaymentDto(
    String paymentId,
    BigDecimal amount,
    String currency,
    Instant capturedAt
) {}
~~~

### 19.1. JSON number và consumer

Jackson có thể deserialize trực tiếp JSON numeric literal vào trường BigDecimal:

~~~json
{
  "paymentId": "PAY-101",
  "amount": 123456789012345.67,
  "currency": "USD",
  "capturedAt": "2026-11-14T08:30:00Z"
}
~~~

Nhưng một consumer JavaScript có thể parse amount thành Number và mất precision, hoặc gateway nào đó chuyển qua double trước khi đến Java.

### 19.2. JSON decimal string contract

Đối với API cần tương thích nhiều ngôn ngữ và số cực lớn:

~~~json
{
  "amount": "123456789012345.67",
  "currency": "USD"
}
~~~

Contract phải công bố amount là decimal string; DTO/serializer cần converter/validation tương ứng. Không thay đổi từ JSON number sang string trong API đang chạy mà không xem backward compatibility.

### 19.3. Giữ scale khi audit

Một API có thể quy định amount luôn hai chữ số lẻ. Khi serialize, cần chuẩn hóa bằng setScale/validator trước, không dựa vào việc formatter ngẫu nhiên in ra 1.0 hay 1.00.

### 19.4. Không serialize floating values không hữu hạn

NaN hoặc Infinity không thuộc JSON number chuẩn. Nếu nguồn có giá trị này, hãy loại bỏ/biểu diễn theo contract riêng, không coi là amount hợp lệ.

## 20. Bảng chọn kiểu số theo nhu cầu

| Bài toán | Java | Lưu NoSQL | Lưu ý |
|---|---|---|---|
| Số lượt xem | long nếu đủ range | Integer/bigint/Number | Atomic increment và retry |
| Giá sản phẩm | BigDecimal/Money | Decimal128/decimal/Number/decimal String | Scale, currency, conversion |
| Số tiền thanh toán | long minor units hoặc Money | Int64/bigint/Number | Overflow, currency fraction digits |
| Tỷ lệ đo cảm biến | double nếu chấp nhận xấp xỉ | Double/float | Sai số đo và threshold |
| Phần trăm thuế chính xác | BigDecimal | decimal/Decimal128 | Quy tắc rounding |
| ID có 20 chữ số | String | String/text | Không parse Number |
| Integer rất lớn | BigInteger | varint/String tùy engine | Range/size/index |
| Điểm xếp hạng search | double/float khi có mô hình xấp xỉ | Search numeric | Không là tiền |

**Chốt ý:** BigDecimal bảo vệ precision trong Java, nhưng chỉ hữu ích khi mọi tầng còn lại giữ decimal semantics và các quy tắc về currency, scale, overflow được định nghĩa.

## 21. Ngày giờ không chỉ là một chuỗi thời gian

Các dữ kiện:

~~~text
Order created at:         2026-11-14T08:30:00Z
User birthday:            1998-03-05
Meeting at local time:    2026-11-14 15:30 Asia/Ho_Chi_Minh
Subscription expires on:  2026-11-30 (the business date)
~~~

có ý nghĩa khác nhau.

### 21.1. Instant: một thời điểm trên trục thời gian

~~~java
import java.time.Instant;

Instant createdAt = Instant.parse("2026-11-14T08:30:00Z");
~~~

Instant không mang timezone hiển thị. Nó là một thời điểm UTC trên timeline, phù hợp với createdAt, committedAt, capturedAt, eventOccurredAt khi có timestamp thực.

### 21.2. LocalDate: một ngày theo lịch

~~~java
import java.time.LocalDate;

LocalDate birthday = LocalDate.parse("1998-03-05");
~~~

Birthday không cần timestamp 00:00 UTC. Đổi ngày sinh thành Instant ở UTC rồi hiển thị tại timezone âm có thể làm đổi ngày.

### 21.3. LocalTime: thời điểm trong ngày không gắn ngày/zone

~~~java
import java.time.LocalTime;

LocalTime storeOpensAt = LocalTime.parse("09:00");
~~~

Nếu cửa hàng mở 09:00 hằng ngày theo giờ địa phương, cần giữ **timezone/zoneId của cửa hàng** ở nơi khác để diễn giải theo ngày thực tế.

### 21.4. LocalDateTime: ngày giờ nhưng không có zone/offset

~~~java
import java.time.LocalDateTime;

LocalDateTime meetingLocal =
        LocalDateTime.parse("2026-11-14T15:30:00");
~~~

Nó chưa xác định một Instant. Nếu đặt meeting trên nhiều quốc gia, cần biết zone hoặc offset trước khi chuyển sang timestamp có thể so sánh toàn cầu.

### 21.5. OffsetDateTime

~~~java
import java.time.OffsetDateTime;

OffsetDateTime withOffset =
        OffsetDateTime.parse("2026-11-14T15:30:00+07:00");
Instant at = withOffset.toInstant();
~~~

Offset +07:00 là chênh lệch UTC ở thời điểm này, **không thay thế zone rules** cho một lịch lặp nhiều năm.

### 21.6. ZonedDateTime

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime display = at.atZone(zone);
~~~

ZonedDateTime giữ zone rules để chuyển đổi/hiển thị. Với lịch tương lai ở khu vực có DST, hãy giữ IANA ZoneId (ví dụ Europe/Paris) thay vì chỉ offset của ngày hiện tại.

## 22. Java Date và java.time: không dùng cùng một cách cho mọi dữ kiện

### 22.1. java.util.Date

Date biểu diễn một thời điểm với precision milliseconds, nhưng API legacy và tên gọi có thể làm người đọc nghĩ nó chỉ là ngày lịch.

~~~java
import java.time.Instant;
import java.util.Date;

Instant instant = Instant.parse("2026-11-14T08:30:00Z");
Date legacyDate = Date.from(instant);
Instant restored = legacyDate.toInstant();
~~~

### 22.2. Precision bị thu hẹp

~~~java
Instant original =
        Instant.parse("2026-11-14T08:30:00.123456789Z");
Date storedAsDate = Date.from(original);
Instant restored = storedAsDate.toInstant();
~~~

Date chỉ mang milliseconds, vì vậy restored không giữ các nano ngoài mili giây. Không dùng test round-trip Instant nanos so với Date mà kỳ vọng giống tuyệt đối.

### 22.3. java.sql.Timestamp

Đây là kiểu thuộc Java SQL/JDBC legacy, có hành vi riêng về nanos và equality. Không dùng nó làm lựa chọn mặc định chỉ vì NoSQL field tên timestamp. Với Java hiện đại, ưu tiên java.time và converter rõ.

### 22.4. Calendar/timezone defaults

Không để conversion dựa tùy tiện vào ZoneId.systemDefault() trên mỗi server. Container UTC và laptop ở múi giờ khác có thể tạo ngày khác cho cùng input.

## 23. BSON DateTime và MongoDB Java Driver

MongoDB BSON DateTime lưu một số nguyên 64-bit biểu diễn **milliseconds kể từ Unix epoch UTC**. Nó không lưu tên timezone hay nanoseconds.

### 23.1. Ghi Instant bằng Date

~~~java
import java.time.Instant;
import java.util.Date;
import org.bson.Document;

Instant createdAt = Instant.parse("2026-11-14T08:30:00.123Z");

Document doc = new Document("createdAt", Date.from(createdAt))
        .append("status", "CREATED");

collection.insertOne(doc);
~~~

### 23.2. Đọc lại

~~~java
Document stored = collection.find().first();
if (stored != null) {
    Date bsonDate = stored.getDate("createdAt");
    Instant restored = bsonDate.toInstant();
}
~~~

### 23.3. Đừng lưu String rồi kỳ vọng Mongo date range index

~~~json
{
  "createdAt": "2026-11-14T08:30:00Z"
}
~~~

Đây là BSON String, không phải BSON DateTime. Range query/index/collation có semantics theo chuỗi; không được kỳ vọng driver tự convert mọi string thành date.

### 23.4. Date-only field

Đối với ngày sinh/expiryDate theo lịch, có thể lưu String chuẩn yyyy-MM-dd hoặc một representation được schema quy định. Nếu lưu BSON DateTime là midnight UTC thì phải định nghĩa rõ quy tắc không làm đổi ngày khi hiển thị ở múi giờ khác.

### 23.5. Timestamps với nanoseconds

Nếu nghiệp vụ cần nano/microseconds thật, BSON DateTime không đủ. Có thể:

- Lưu epoch seconds + nano adjustment.
- Lưu epoch microseconds trong Int64 nếu range phù hợp.
- Lưu String timestamp với precision cố định.
- Sử dụng engine/kiểu hỗ trợ precision cần thiết.

Mọi cách đều cần thống nhất query/index, migration và Java converter; không chuyển ngầm sang milliseconds.

## 24. DynamoDB: lưu thời gian dạng String hoặc Number

DynamoDB không có scalar DateTime riêng. Các lựa chọn phổ biến:

### 24.1. Chuỗi ISO-8601 UTC

~~~json
{
  "createdAt": "2026-11-14T08:30:00.123Z"
}
~~~

Ưu điểm:

- Dễ đọc/log/debug.
- Có thể làm sort key theo thứ tự từ điển **nếu format được chuẩn hóa**.
- Tương thích nhiều ngôn ngữ.

### 24.2. Epoch milliseconds

~~~json
{
  "createdAtEpochMs": 1794645000123
}
~~~

Đây là ví dụ biểu diễn một timestamp theo quy ước epoch milliseconds; giá trị số thực tế phải do Java Instant.toEpochMilli() tính từ Instant được yêu cầu, không tự lấy ví dụ rồi coi là chính xác cho mọi thời điểm.

### 24.3. Quy tắc quan trọng cho String sort key

Chỉ dùng so sánh chuỗi làm chronological ordering khi:

- Luôn cùng timezone UTC.
- Cùng độ dài và cách biểu diễn fractional seconds.
- Cùng format, cùng chuẩn padded năm/tháng/ngày/giờ.
- Không trộn strings có +07:00 với Z hay thiếu offset.

Ví dụ:

~~~text
2026-11-14T08:30:00.000Z
2026-11-14T08:30:00.001Z
2026-11-14T08:30:00.100Z
~~~

Chúng có format cố định và sort theo thời gian trong phạm vi năm thông dụng.

### 24.4. ISO_INSTANT không luôn fixed-width fraction

Một số formatters có thể bỏ phần .000 khi không cần, khiến:

~~~text
2026-11-14T08:30:00Z
2026-11-14T08:30:00.001Z
~~~

không sort theo thứ tự mong đợi khi so byte như String vì ký tự dấu chấm đứng trước Z. Nếu dùng String làm sort key, hãy xây một formatter có **fractional width cố định**.

### 24.5. Java formatter cố định milliseconds ở UTC

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public static final DateTimeFormatter SORTABLE_UTC =
        DateTimeFormatter.ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS'Z'")
                .withZone(ZoneOffset.UTC);

String sortValue = SORTABLE_UTC.format(
        Instant.parse("2026-11-14T08:30:00.123Z")
);
~~~

Nếu dữ liệu chứa precision nhỏ hơn milliseconds hoặc ngoài năm 4 chữ số, phải định nghĩa cách thu hẹp/biểu diễn trước khi dùng format này cho toàn miền dữ liệu.

### 24.6. TTL trong DynamoDB

DynamoDB TTL thường yêu cầu một Number biểu diễn **Unix epoch seconds** ở attribute được cấu hình, khác với createdAtEpochMs.

~~~text
createdAtEpochMs = eventInstant.toEpochMilli()
expiresAtEpochSeconds = expiryInstant.getEpochSecond()
~~~

Không dùng milliseconds làm TTL seconds hoặc nhầm TTL là cam kết xóa đúng tức thời; cơ chế TTL là asynchronous theo dịch vụ.

## 25. Cassandra/ScyllaDB: timestamp, date và time

CQL thường có:

- timestamp: thời điểm với precision milliseconds theo kiểu.
- date: ngày theo lịch.
- time: thời gian trong ngày với nanosecond-resolution representation của CQL.

### 25.1. Java mapping thông dụng

| CQL | Java type thường dùng | Ý nghĩa |
|---|---|---|
| timestamp | Instant | Một thời điểm, milliseconds precision |
| date | LocalDate | Ngày theo lịch |
| time | LocalTime | Thời gian trong ngày |
| text với timezone | String/ZoneId converter | Business timezone ID |

### 25.2. CQL ví dụ

~~~sql
CREATE TABLE sessions_by_user (
  tenant_id text,
  user_id uuid,
  session_id uuid,
  created_at timestamp,
  birth_date date,
  preferred_time time,
  timezone_id text,
  PRIMARY KEY ((tenant_id, user_id), session_id)
);
~~~

### 25.3. Đừng nhầm timestamp với timestamp do Cassandra sinh

Một CQL timestamp field là một giá trị dữ liệu. Nó khác với write timestamp nội bộ dùng trong conflict resolution/cell writes. Cùng chữ timestamp không nghĩa chúng có cùng mục đích hoặc precision.

### 25.4. Date trong partition key

Nếu partition theo date:

~~~text
PK=(deviceId, activityDay)
~~~

phải thống nhất activityDay dựa trên UTC, device timezone hay business timezone. Nếu service A tính theo UTC còn service B theo America/New_York, cùng event có thể vào hai partitions khác nhau.

## 26. Khi nào cần lưu timezone cùng timestamp?

### 26.1. Event đã xảy ra

Một log ghi thao tác tạo đơn:

~~~text
createdAt = Instant
~~~

Thường đủ để so thời gian và audit. Có thể lưu display zone bổ sung nếu có yêu cầu pháp lý hoặc trải nghiệm người dùng.

### 26.2. Lịch hẹn theo giờ địa phương tương lai

~~~text
meetingLocalTime = 09:00
meetingLocalDate = 2027-04-12
zoneId = Europe/Paris
~~~

Chỉ lưu một offset +01:00 tính từ lúc tạo lịch không đủ cho DST ở ngày hẹn. Cần giữ ZoneId để diễn giải đúng giờ địa phương khi luật timezone thay đổi.

### 26.3. Subscription theo ngày kinh doanh

~~~text
expiresOn = 2026-11-30
businessZone = Asia/Ho_Chi_Minh
~~~

Ngày hết hạn có thể có nghĩa “đến cuối ngày 30/11 theo timezone doanh nghiệp”, không phải instant 00:00Z. Contract cần nói rõ boundary inclusive/exclusive.

### 26.4. Không chỉ lưu local wall time nếu cần so sánh toàn cầu

~~~text
2026-11-14 15:30
~~~

không có zone thì không biết là 15:30 tại đâu. Để ghi log và sort events xuyên Region, cần Instant hoặc đủ zone/offset để resolve.

## 27. DST, giờ không tồn tại và giờ lặp

### 27.1. Giờ không tồn tại

Ở một số khu vực đổi từ giờ mùa đông sang mùa hè, đồng hồ nhảy qua một khoảng. Một local time như 02:30 vào ngày chuyển DST có thể **không tồn tại**.

### 27.2. Giờ lặp

Khi đồng hồ lùi lại, cùng local 01:30 hoặc 02:30 có thể xảy ra hai lần với offsets khác nhau.

### 27.3. Đừng chuyển LocalDateTime mù quáng

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime local =
        LocalDateTime.parse("2026-10-25T02:30:00");
ZoneId zone = ZoneId.of("Europe/Paris");
ZonedDateTime resolved = local.atZone(zone);
~~~

Java có quy tắc mặc định để resolve gap/overlap. Nhưng nếu nghiệp vụ đặt lịch yêu cầu người dùng chọn rõ “lần 02:30 thứ nhất hay thứ hai”, cần validate ZoneRules và yêu cầu offset/choice, không âm thầm chấp nhận mặc định.

### 27.4. Khoảng ngày nên dùng half-open interval

Để query một ngày theo timezone doanh nghiệp:

~~~java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

LocalDate day = LocalDate.parse("2026-11-14");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

// Query: timestamp >= start && timestamp < end
~~~

Khoảng [start, end) tránh việc hardcode 23:59:59.999 và xử lý tốt hơn ngày có độ dài không đúng 24 giờ do DST ở các khu vực khác.

## 28. Precision thời gian: seconds, milliseconds, microseconds, nanoseconds

### 28.1. Một bảng đơn vị

| Đơn vị | Ví dụ giá trị trong một giây | Khoảng cách |
|---|---|---|
| seconds | 08:30:00 | 1 giây |
| milliseconds | 08:30:00.123 | 1/1.000 giây |
| microseconds | 08:30:00.123456 | 1/1.000.000 giây |
| nanoseconds | 08:30:00.123456789 | 1/1.000.000.000 giây |

### 28.2. Sự khác nhau trong Java

Instant có nanosecond adjustment, nhưng storage như BSON DateTime/CQL timestamp thường chỉ giữ milliseconds. Conversion phải **có chủ đích**; nếu cần thứ tự chính xác tới microseconds, đừng dựa trên milliseconds làm unique key.

### 28.3. Java conversion

~~~java
Instant at = Instant.parse("2026-11-14T08:30:00.123456Z");

long epochSeconds = at.getEpochSecond();
long epochMillis = at.toEpochMilli();
int nanos = at.getNano();
~~~

getNano() là phần nanoseconds **trong giây hiện tại**, không phải tổng nanoseconds kể từ epoch.

### 28.4. Epoch millis và seconds

Sai:

~~~text
Store expiresAt = epochMillis
TTL expects epochSeconds
~~~

Khác nhau 1.000 lần. Cần đặt tên field có đơn vị và converter riêng.

### 28.5. Overflow và range

Instant có miền thời gian rộng hơn nhiều cách encode kiểu signed 64-bit milliseconds hoặc nanoseconds. toEpochMilli và các phép nhân thời gian có thể ném lỗi/overflow với thời điểm ngoài phạm vi. Validate range cho timestamp nhận từ input.

## 29. Jackson và Java time types

Jackson JSON mapping với java.time thường cần module JSR-310:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

### 29.1. DTO có Instant/LocalDate

~~~java
import java.time.Instant;
import java.time.LocalDate;

public record CustomerDto(
    String id,
    LocalDate birthday,
    Instant registeredAt
) {}
~~~

Với cấu hình formatter thích hợp, API có thể chọn:

~~~json
{
  "id": "U101",
  "birthday": "1998-03-05",
  "registeredAt": "2026-11-14T08:30:00Z"
}
~~~

### 29.2. Không ép birthday thành 00:00 UTC

Một LocalDate được serialize thành yyyy-MM-dd giữ đúng ngày. Nếu Java DTO lại dùng Date/Instant thì mọi consumer phải chuyển timezone và có thể hiển thị ngày trước đó.

### 29.3. Không để parser tin vào server default timezone

Một chuỗi LocalDateTime không offset có thể bị diễn giải khác nhau nếu converter dựa trên machine default. Chọn contract: bắt buộc offset/UTC cho event timestamp, hoặc giữ local+zoneId cho lịch.

### 29.4. Mapper khác nhau có thể cho JSON khác nhau

Driver trực tiếp, Spring Data converters, Jackson API serializers và custom codecs có những quy tắc riêng. Một field hiển thị đúng ở REST không chứng minh nó được lưu đúng xuống BSON/NoSQL.

## 30. Quy tắc chọn thời gian theo yêu cầu

| Dữ kiện | Java | Lưu trữ có thể chọn | Điều cần giữ |
|---|---|---|---|
| createdAt / updatedAt | Instant | BSON DateTime/CQL timestamp/epoch ms | UTC, milliseconds nếu storage giới hạn |
| Birthday | LocalDate | CQL date/String yyyy-MM-dd | Ngày lịch, không ép UTC |
| Business expiry date | LocalDate + ZoneId | Date String + businessZone | Inclusive/exclusive boundary |
| Appointment ở zone cụ thể | LocalDateTime + ZoneId hoặc ZonedDateTime | Local fields + IANA zone | DST/overlap/gap |
| Payment capturedAt | Instant | Source timestamp | Durability, ordering, provenance |
| Search sort createdAt | Instant | epoch number hoặc canonical UTC String | Consistent units/width |
| Session TTL | Instant/Duration | Epoch seconds theo engine | TTL semantics, clock skew |
| Event time-series | Instant | Timestamp + ID/bucket | Precision, late-arrival policy |

**Chốt ý:** Lưu đúng đơn vị và khái niệm thời gian quan trọng hơn việc mọi database đều nhận được một Date object.

## 31. Dữ liệu lồng nhau: object, array, map và document

Một Order có địa chỉ giao hàng và danh sách sản phẩm:

~~~json
{
  "orderId": "O101",
  "shipping": {
    "recipient": "An",
    "address": {
      "country": "VN",
      "city": "Hồ Chí Minh",
      "postalCode": "700000"
    }
  },
  "items": [
    {
      "productId": "P501",
      "quantity": 2,
      "unitPriceMinor": 1200000
    }
  ],
  "attributes": {
    "channel": "mobile",
    "campaign": "NOVEMBER"
  }
}
~~~

Java model tương ứng:

~~~java
import java.util.List;
import java.util.Map;

public record Address(
        String country,
        String city,
        String postalCode
) {}

public record Shipping(
        String recipient,
        Address address
) {}

public record OrderLine(
        String productId,
        int quantity,
        long unitPriceMinor
) {}

public record Order(
        String orderId,
        Shipping shipping,
        List<OrderLine> items,
        Map<String, String> attributes
) {}
~~~

### 31.1. Embedded object khác reference

- **Embedded:** Shipping/Address nằm trong một Order document.
- **Reference:** Order chỉ lưu addressId rồi truy vấn Address từ document khác.

Embedded giảm round trips và giữ data locality; nhưng update, document size, lịch sử snapshot và reuse có trade-offs.

### 31.2. Snapshot địa chỉ giao hàng

ShippingAddress trong Order có thể là snapshot tại lúc mua, không nên thay đổi chỉ vì Customer.profile.address hiện tại thay đổi.

### 31.3. List có thứ tự, Set không?

Java List giữ thứ tự và cho phép phần tử trùng. Set không cho phần tử trùng theo equality semantics và thứ tự iteration không mặc định ổn định. NoSQL arrays/sets có semantics riêng; không map List<OrderLine> thành Set chỉ để loại duplicate nếu duplicate lines mang ý nghĩa.

### 31.4. Map key là dữ liệu

Với Map<String,String> attributes, keys có thể phát sinh từ user input. Cần validate allowlist, kích thước, encoding và ký tự để tránh field explosion/query injection.

### 31.5. Nested arrays có thể tốn chi phí

Nếu một Order chứa hàng trăm nghìn line items, embedded list có thể vượt giới hạn document hoặc khiến update/document rewrite rất nặng. Cân nhắc separate collection/table và identity/order của line items.

## 32. Java MongoDB Driver: Document lồng nhau

### 32.1. Ghi embedded Document

~~~java
import org.bson.Document;
import java.util.List;

Document address = new Document("country", "VN")
        .append("city", "Hồ Chí Minh")
        .append("postalCode", "700000");

Document shipping = new Document("recipient", "An")
        .append("address", address);

Document line = new Document("productId", "P501")
        .append("quantity", 2)
        .append("unitPriceMinor", 1200000L);

Document order = new Document("_id", "O101")
        .append("shipping", shipping)
        .append("items", List.of(line));

collection.insertOne(order);
~~~

### 32.2. Đọc embedded Document an toàn

~~~java
Document found = collection.find(
        new Document("_id", "O101")
).first();

if (found != null) {
    Document storedShipping =
            found.get("shipping", Document.class);
    if (storedShipping != null) {
        Document storedAddress =
                storedShipping.get("address", Document.class);
        if (storedAddress != null) {
            String city = storedAddress.getString("city");
        }
    }
}
~~~

Nếu shipping có kiểu String do dữ liệu legacy, typed getter có thể ném ClassCastException. Trong hệ có schema evolution, cần kiểm tra/convert legacy trước khi cast.

### 32.3. Partial update bằng dot notation

~~~java
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.Filters;

collection.updateOne(
        Filters.eq("_id", "O101"),
        Updates.set("shipping.address.city", "Đà Nẵng")
);
~~~

Đây là cập nhật một path, khác với thay toàn bộ shipping object. Nó phù hợp khi thay riêng city và vẫn giữ country/postalCode.

### 32.4. Whole-object replacement có thể làm mất field

Một update kiểu:

~~~text
SET shipping = {recipient:"An", address:{city:"Đà Nẵng"}}
~~~

có thể làm mất country và postalCode nếu không include đầy đủ.

### 32.5. Array update

Các update operators cho array như positional/array filters có semantics theo query và version engine. Không lấy index của một array tại thời điểm t1 rồi cập nhật ở t2 khi concurrent writers có thể thêm/xóa/reorder phần tử.

Nếu cần identity ổn định từng line, lưu lineId hoặc tách line thành documents.

### 32.6. Kích thước document

MongoDB có giới hạn kích thước BSON document (thường 16 MiB với MongoDB), nên embedding tất cả lịch sử events của một customer vào một document có thể không khả thi. Cân nhắc access pattern, tăng trưởng và write amplification.

## 33. MongoDB POJO codecs, Jackson và Spring Data không phải cùng một mapper

### 33.1. Ba ranh giới

~~~text
REST JSON <-- Jackson --> Java DTO
Java domain <-- custom mapping --> Persistence model
Persistence model <-- MongoDB codecs --> BSON
~~~

Spring Data MongoDB có converters/annotations riêng, còn MongoDB Java Driver có codec registries và POJO codec infrastructure. Một annotation chỉ dành cho Jackson không tự bảo đảm MongoDB sẽ xử lý field giống vậy.

### 33.2. Tách public ID khỏi storage ID

Một REST DTO:

~~~java
public record OrderResponse(
        String id,
        String orderNumber
) {}
~~~

Một persistence model:

~~~java
import org.bson.types.ObjectId;

public record StoredOrder(
        ObjectId id,
        String orderNumber
) {}
~~~

Repository hoặc mapper chuyển ObjectId ↔ String ở boundary. Một framework có thể đòi cách cấu hình/constructor riêng cho record; không coi ví dụ record này là universal automatic POJO mapping.

### 33.3. Custom value converters

Nếu muốn domain giữ CustomerId(UUID) nhưng lưu BSON String, custom converter phải có hai chiều:

~~~text
write: CustomerId(UUID) -> UUID canonical String
read:  UUID canonical String -> CustomerId(UUID)
~~~

Migration từ BSON Binary UUID sang String cần hỗ trợ dữ liệu legacy có kiểm chứng; không đổi converter đột ngột khiến query bằng ID bị trượt.

### 33.4. Đừng để HTTP mapper quyết định persistence contract ngầm

Một Jackson @JsonProperty("order_id") không nhất thiết đổi tên BSON field trong MongoDB. Cần explicit mapping/annotations theo framework thực sự dùng và test round-trip.

## 34. DynamoDB: Map, List, Set và các kiểu AttributeValue

DynamoDB dùng AttributeValue với nhiều kiểu:

- S: String.
- N: Number được biểu diễn trong API bằng chuỗi số.
- B: Binary.
- BOOL: Boolean.
- NULL: Null marker.
- M: Map.
- L: List.
- SS/NS/BS: String/Number/Binary Set.

### 34.1. AWS SDK Java v2 tạo Map lồng nhau

~~~java
import java.util.Map;
import java.util.List;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

AttributeValue address = AttributeValue.builder()
        .m(Map.of(
                "country", AttributeValue.builder().s("VN").build(),
                "city", AttributeValue.builder().s("Hồ Chí Minh").build(),
                "postalCode", AttributeValue.builder().s("700000").build()
        ))
        .build();

AttributeValue item1 = AttributeValue.builder()
        .m(Map.of(
                "productId", AttributeValue.builder().s("P501").build(),
                "quantity", AttributeValue.builder().n("2").build()
        ))
        .build();

Map<String, AttributeValue> order = Map.of(
        "PK", AttributeValue.builder().s("ORDER#O101").build(),
        "address", address,
        "items", AttributeValue.builder().l(List.of(item1)).build()
);
~~~

### 34.2. Đọc nested values

~~~java
AttributeValue rawAddress = order.get("address");
String city = rawAddress.m().get("city").s();

AttributeValue rawItems = order.get("items");
String firstProductId = rawItems.l()
        .get(0).m().get("productId").s();
~~~

Đây là đường đọc khi dữ liệu đã đúng schema và items không rỗng. Trước khi truy cập production cần validate kiểu, key tồn tại và list size.

### 34.3. List khác Set

List có thứ tự và có thể chứa duplicate values; DynamoDB Set không lưu duplicate trong tập và empty set bị hạn chế theo API.

Nếu orderLine A và orderLine B cùng productId nhưng là hai mục riêng, không chuyển thành String Set chỉ vì muốn tiết kiệm dữ liệu.

### 34.4. DynamoDB Map có thể chứa dữ liệu hỗn hợp

Map hỗ trợ các AttributeValue nested tùy giới hạn của dịch vụ. Sự linh hoạt này không có nghĩa consumer được skip validation; cần xác định những field bắt buộc và version schema.

### 34.5. Partial update

DynamoDB UpdateExpression có thể cập nhật một map path, nhưng expression attribute names/values và việc tạo parent map phải theo quy tắc của API. Không tự xây path từ raw field name không được validate.

### 34.6. Nested object và size limit

DynamoDB items có giới hạn kích thước (thường 400 KB/item). Một List 100.000 events không nên nhét vào một item chỉ để thuận tiện object mapping.

## 35. Cassandra/ScyllaDB: collections, tuple và UDT

Một hệ wide-column có thể dùng:

- list<text>: danh sách.
- set<text>: tập.
- map<text,text>: map.
- User-Defined Type (UDT): object có các fields định nghĩa trước.
- tuple: nhóm giá trị positional.

### 35.1. UDT cho địa chỉ

~~~sql
CREATE TYPE shipping_address (
  country text,
  city text,
  postal_code text
);

CREATE TABLE orders_by_id (
  tenant_id text,
  order_id uuid,
  shipping frozen<shipping_address>,
  tags set<text>,
  attributes map<text, text>,
  PRIMARY KEY ((tenant_id, order_id))
);
~~~

Cú pháp phụ thuộc keyspace/schema hiện hành của môi trường; ví dụ có mục đích minh họa modeling.

### 35.2. Frozen UDT

Một frozen UDT được xử lý như một giá trị tổng thể trong nhiều thao tác, khiến update một field bên trong thường phải thay toàn bộ frozen value. Điều này ảnh hưởng đồng thời updates và write amplification.

### 35.3. Không embed tập dữ liệu tăng vô hạn

Một collection lớn có hàng chục nghìn events sẽ làm partition/row nóng và các updates tốn tài nguyên. Cần chuyển sang bảng riêng theo access pattern:

~~~text
events_by_order((tenantId,orderId), occurredAt,eventId)
~~~

### 35.4. Map/Set ordering

Không dựa vào iteration order của Map/Set trong Java hoặc CQL để xây business sequence. Nếu thứ tự quan trọng, lưu một sort key/sequence.

### 35.5. UDT evolution

Thêm/sửa fields trong UDT cần xem tính tương thích driver/schema, các nodes và records cũ. Không coi class Java mới có thêm field sẽ làm data cũ tự nhận đúng default.

## 36. Redis: nested data qua Hash, JSON và serialization contract

### 36.1. Redis Hash

~~~text
HSET order:O101 status CONFIRMED totalMinor 1200000 currency VND
~~~

Hash có các field/value theo encoding Redis; không có Java record schema được enforce tự động.

### 36.2. JSON string

~~~text
SET order:O101 "{\"status\":\"CONFIRMED\",\"items\":[]}"
~~~

Đây là một String chứa JSON. Nếu dùng RedisJSON extension, cách thao tác nested path khác và phải có module/commands tương ứng.

### 36.3. Update whole JSON

Hai writers đọc cùng value, sửa hai nested fields khác nhau rồi SET lại toàn JSON có thể làm mất update của nhau:

~~~text
Writer A reads v7, changes address.
Writer B reads v7, changes status.
Writer A SET v8/address.
Writer B SET v8/status, restoring old address.
~~~

Tránh bằng conditional version/CAS, transaction/Lua hoặc tách fields theo access pattern khi cần.

### 36.4. Serialization compatibility

Nếu lưu một Java-serialized binary object, class changes có thể khiến data cũ khó đọc và khó chia sẻ với ngôn ngữ khác. Ưu tiên format có schema/version rõ, trừ khi có lý do kiểm soát môi trường.

### 36.5. Redis cache không tự là nguồn chuẩn

Đối với một cached OrderSummary, chỉ nên tái tạo từ authoritative Order source khi cache mất, thay vì phục hồi source ngược từ String JSON cache chưa chắc mới nhất.

## 37. Dữ liệu lồng nhau: null, missing, empty và default là bốn trường hợp

Ví dụ:

~~~json
{"orderId":"O101"}
~~~

~~~json
{"orderId":"O101","shipping":null}
~~~

~~~json
{"orderId":"O101","shipping":{}}
~~~

~~~json
{"orderId":"O101","items":[]}
~~~

### 37.1. Missing

Field không tồn tại: có thể là document version cũ, chưa được cập nhật, hoặc field optional.

### 37.2. Explicit null

Field có tồn tại với giá trị null: có thể mang ý nghĩa “đã xóa/không biết/không áp dụng”, tùy contract.

### 37.3. Empty object

Object rỗng không giống null: có thể là một cấu trúc đã khởi tạo nhưng chưa có fields.

### 37.4. Empty list

Danh sách rỗng thường có nghĩa xác định “không có phần tử”, không giống danh sách chưa được tải hoặc field chưa có trong schema cũ.

### 37.5. Java primitive và boxed type

~~~java
int quantity;      // default 0
Integer quantity;  // có thể null
~~~

Nếu JSON thiếu quantity nhưng mapper gán 0, ứng dụng có thể không phân biệt chưa có dữ liệu với số lượng thật bằng 0.

### 37.6. MongoDB query null

Trong MongoDB, so sánh field với null có thể match cả trường null lẫn không tồn tại tùy operator. Nếu business logic cần phân biệt, dùng điều kiện existence/type phù hợp thay vì xem query equality null là cùng một nghĩa với explicit-null-only.

### 37.7. DynamoDB NULL khác absent

AttributeValue NULL là một marker; không có attribute là absent. ConditionExpression có các semantics khác nhau cho attribute_exists, attribute_not_exists và type checks; hãy định nghĩa chúng trong business contract.

## 38. PATCH: field thiếu khác với yêu cầu xóa field

Một API cập nhật hồ sơ:

~~~json
{
  "displayName": "An"
}
~~~

có thể mang nghĩa chỉ sửa displayName, giữ nguyên phone.

Trong khi:

~~~json
{
  "phone": null
}
~~~

có thể được định nghĩa là xóa phone, hoặc là invalid input tùy API.

### 38.1. Tránh dùng DTO null không phân biệt trạng thái

Nếu cùng Java DTO có phone=null cho cả JSON missing và JSON explicit null, repository không biết cần giữ hay xóa field.

### 38.2. Một cách mô hình hóa tri-state

~~~java
public record PatchValue<T>(boolean present, T value) {
    public static <T> PatchValue<T> absent() {
        return new PatchValue<>(false, null);
    }
    public static <T> PatchValue<T> of(T value) {
        return new PatchValue<>(true, value);
    }
}
~~~

Ứng dụng cần parser/mapping nhận biết field có xuất hiện trong JSON, ví dụ qua JsonNode.has(), để tạo PatchValue phù hợp. Tự dùng record này không khiến Jackson tự map missing vs explicit null đúng.

### 38.3. PUT và PATCH không mặc định giống nhau

Theo API contract, PUT thường diễn giải thay thế representation, còn PATCH áp dụng thay đổi có chọn lọc. Cần công bố semantics cụ thể, đặc biệt với nested objects và arrays.

### 38.4. Delete nested field

MongoDB có thể dùng $unset; DynamoDB có REMOVE path; CQL/Redis có các thao tác tương ứng. Không nhất thiết đặt null là tương đương xóa field.

### 38.5. Optimistic concurrency

Khi hai clients sửa những phần khác nhau của nested object, dùng version/CAS hoặc atomic path updates để tránh lost update; không luôn replace toàn bộ document từ một snapshot cũ.

## 39. Polymorphic nested values và security

### 39.1. Dữ liệu nhiều loại

Một activity có thể là:

~~~text
PaymentEvent
ShipmentEvent
CustomerEvent
~~~

Trong JSON/BSON có thể dùng explicit discriminator:

~~~json
{
  "kind": "PAYMENT_CAPTURED",
  "schemaVersion": 2,
  "data": {
    "paymentId": "P101",
    "amountMinor": 1200000
  }
}
~~~

### 39.2. Không để raw payload chọn class bất kỳ

Không bật polymorphic deserialization cho phép input không tin cậy chỉ định tên Java class bất kỳ. Dùng allowlist các event kinds đã biết và converter cụ thể.

### 39.3. Unknown kind

Nếu consumer cũ nhận event kind mới, cần policy rõ:

- Preserve/skip theo hợp đồng.
- Quarantine vào dead-letter queue.
- Nâng phiên bản consumer.

Không deserialize mù rồi silently drop business-critical event.

### 39.4. Dynamic field keys

Người dùng nhập key có dấu chấm, ký tự đặc biệt hoặc từ giống operator của query có thể làm map/update path khó kiểm soát.

Validate fields theo schema, không nối trực tiếp untrusted key vào MongoDB update operator/NoSQL expression. Một số engine hỗ trợ tên field đặc biệt với các giới hạn riêng; cần xem API cụ thể thay vì tin mọi chuỗi đều là path an toàn.

## 40. Nhúng hay tham chiếu? Quy tắc chọn

| Câu hỏi | Embedded object | Reference/separate collection |
|---|---|---|
| Cùng đọc với parent gần như mọi lúc? | Thường tốt | Có thể thêm round trip |
| Object nhỏ và có giới hạn? | Phù hợp | Không bắt buộc |
| Object lớn/tăng không giới hạn? | Dễ vượt item/doc size | Thường tốt hơn |
| Có update độc lập rất thường xuyên? | Có thể write contention | Dễ scale theo key riêng |
| Cần snapshot lịch sử? | Embedding có thể đúng ý nghĩa | Cần version/lookup lịch sử |
| Được nhiều owners sửa? | Rủi ro chia ownership | Cần boundary/domain rõ |
| Query riêng theo child fields? | Tùy index/engine | Có thể phù hợp |
| Có invariant atomic cùng parent? | Có lợi nếu engine atomic document/item | Cross-key có thể cần transaction |

**Chốt ý:** Mapping nested object phải phản ánh access pattern và quyền sở hữu dữ liệu, không chỉ cấu trúc class Java.

## 41. Ví dụ tổng hợp: một Payment document với đủ bốn nhóm kiểu

Giả sử MongoDB làm kho có thẩm quyền cho payment metadata trong phạm vi một Payment Service. Bản ghi cần:

- ID kỹ thuật ObjectId.
- Business ID và tenant ID dạng String.
- Amount chính xác BigDecimal/Decimal128.
- Timestamp Instant/BSON DateTime.
- Address nested Document.
- Tags dạng List<String>.

### 41.1. Java persistence object

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;

public record PaymentDocument(
        ObjectId id,
        String tenantId,
        String paymentId,
        BigDecimal amount,
        String currency,
        Instant createdAt,
        Address billingAddress,
        List<String> tags
) {}
~~~

### 41.2. Mapping Java → BSON Document

~~~java
import java.util.Date;
import org.bson.Document;
import org.bson.types.Decimal128;

public static Document toBson(PaymentDocument p) {
    Document address = new Document("country", p.billingAddress().country())
            .append("city", p.billingAddress().city())
            .append("postalCode", p.billingAddress().postalCode());

    return new Document("_id", p.id())
            .append("tenantId", p.tenantId())
            .append("paymentId", p.paymentId())
            .append("amount", new Decimal128(p.amount()))
            .append("currency", p.currency())
            .append("createdAt", Date.from(p.createdAt()))
            .append("billingAddress", address)
            .append("tags", p.tags());
}
~~~

Ví dụ giả định billingAddress không null, amount nằm trong Decimal128 range và createdAt có precision phù hợp. Các điều kiện này nên được validate trong domain/repository.

### 41.3. BSON Document → Java

~~~java
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.bson.types.ObjectId;

public static PaymentDocument fromBson(Document d) {
    Document a = d.get("billingAddress", Document.class);
    if (a == null) {
        throw new IllegalArgumentException("billing address required");
    }

    List<?> rawTags = d.getList("tags", Object.class);
    if (rawTags == null) {
        throw new IllegalArgumentException("tags required");
    }
    List<String> tags = rawTags.stream()
            .map(value -> {
                if (!(value instanceof String s)) {
                    throw new IllegalArgumentException("tag must be String");
                }
                return s;
            })
            .toList();

    return new PaymentDocument(
            d.get("_id", ObjectId.class),
            d.getString("tenantId"),
            d.getString("paymentId"),
            d.get("amount", Decimal128.class).bigDecimalValue(),
            d.getString("currency"),
            d.getDate("createdAt").toInstant(),
            new Address(
                    a.getString("country"),
                    a.getString("city"),
                    a.getString("postalCode")
            ),
            tags
    );
}
~~~

Đoạn minh họa sử dụng Java hiện đại có pattern matching instanceof và Stream.toList(). Trong ứng dụng cần xử lý nullable/legacy types, validation và exceptions theo error contract thay vì chỉ để NullPointerException lộ ra.

### 41.4. Một ranh giới API khác

API có thể dùng String id:

~~~java
public record PaymentResponse(
        String id,
        String paymentId,
        String amount,
        String currency,
        String createdAt
) {}
~~~

Repository/controller map từ PaymentDocument sang DTO; không để caller biết _id BSON là ObjectId nếu API cam kết opaque String ID.

### 41.5. Không làm tròn âm thầm

Nếu amount có 8 chữ số sau dấu thập phân, nhưng business contract chỉ cho scale=2, converter không được tự cắt thành 2 nếu chưa có rounding policy. Validate và trả lỗi hoặc áp dụng rounding theo nghiệp vụ đã được định nghĩa.

### 41.6. Không làm sai createdAt

Nếu p.createdAt() chứa nanoseconds, Date.from sẽ làm mất precision dưới milliseconds. Nếu business yêu cầu nano, storage model này phải thay đổi; không thể sửa bằng formatter lúc trả API.

## 42. DTO, domain model, persistence model: có nên dùng một class duy nhất?

### 42.1. Một class có thể đủ cho ứng dụng đơn giản

Với một CRUD nhỏ, dùng một DTO/POJO cho cả API và storage có thể giảm code.

### 42.2. Nhưng ranh giới có lý do tồn tại

Một hệ nhiều clients/migration thường cần:

~~~text
API DTO
  id: String
  amount: decimal String
  birthday: yyyy-MM-dd

Domain
  id: PaymentId
  amount: Money
  createdAt: Instant

Persistence
  _id: ObjectId
  amount: Decimal128
  createdAt: BSON DateTime
~~~

Mapper làm rõ conversion. Domain model không phụ thuộc MongoDB ObjectId nếu team muốn có khả năng thay storage hoặc dùng một business ID xuyên các services.

### 42.3. Chi phí của nhiều models

Thêm mapper khiến code dài hơn, nhưng có lợi khi:

- Public API khác storage schema.
- Cần bảo vệ invariants.
- Có dữ liệu legacy.
- Nhiều providers/drivers.
- Đổi backend dần dần.

Không tạo ba lớp giống hệt nhau chỉ vì hình thức. Chọn ranh giới có lý do kỹ thuật.

### 42.4. Mapping phải deterministic

Cùng input hợp lệ và cùng schema version phải cho cùng output chuẩn; tránh lấy current time/default timezone/random ID một cách ngầm trong read mapper.

Nếu cần createdAt hoặc ID mới, sinh tại command creation boundary và ghi lại, không sinh lại mỗi lần deserialize.

## 43. Schema evolution: các documents cũ và mới sống cùng nhau

NoSQL thường cho phép những bản ghi có schema khác nhau:

~~~json
{"_id":"O101","amount":120.5}
~~~

~~~json
{
  "_id": "O102",
  "amount": "120.50",
  "currency": "USD",
  "schemaVersion": 2
}
~~~

~~~json
{
  "_id": "O103",
  "totalMinor": 12050,
  "currency": "USD",
  "schemaVersion": 3
}
~~~

### 43.1. Một mapper duy nhất không thể cast mù

Code:

~~~java
long total = doc.getLong("totalMinor");
~~~

có thể lỗi khi field không tồn tại hoặc type cũ khác. Cần mapping theo schemaVersion/shape và migration policy.

### 43.2. Read old, write new

Trong giai đoạn nâng cấp:

1. Readers mới hiểu cả schema v1/v2.
2. Writers mới chỉ ghi schema v2.
3. Backfill dữ liệu cũ có checkpoint.
4. Đo số records còn legacy.
5. Khi không còn clients/records cũ, gỡ converter tương thích.

### 43.3. Không âm thầm “sửa” số đã mất precision

Nếu v1 lưu Double, đổi thành Decimal128 ở v2 không khôi phục decimal người dùng nhập ban đầu. Phải xác định cách chuyển đổi/audit và nguồn đối soát như invoice/ledger nếu có.

### 43.4. Field rename

~~~text
v1: shipTo.city
v2: shipping.address.city
~~~

Trong migration, mapper có thể đọc cả hai, nhưng writer nên có representation rõ và không cho hai giá trị xung đột cùng điều khiển business logic.

### 43.5. Schema version không phải business version

schemaVersion=3 nói record dùng định dạng v3; aggregateVersion=12 nói dữ liệu đã trải 12 phiên bản thay đổi nghiệp vụ. Không trộn hai loại version này.

### 43.6. Bản ghi thiếu field

Một field mới shippingInstructions optional có thể vắng mặt ở dữ liệu cũ. Không mặc định field vắng mặt là null có cùng nghĩa với user chủ động xóa instructions.

## 44. Migration định danh: ObjectId, String, UUID

Một ứng dụng trước dùng ObjectId và muốn chuyển public API sang UUID. Rủi ro:

- External clients đang lưu ObjectId hex.
- Cross-service references vẫn dùng ID cũ.
- Search documents dùng old ID làm key.
- Cache keys và idempotency references phụ thuộc format cũ.
- Một số records có _id type khác.

### 44.1. Đừng sửa primary IDs hàng loạt mà không lập bản đồ tham chiếu

Có thể thêm publicId ổn định:

~~~json
{
  "_id": {"$oid":"507f1f77bcf86cd799439011"},
  "publicId": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Sau đó xây unique index/lookup cho publicId và cập nhật API dần theo một migration plan. Đây là Extended JSON minh họa kiểu ObjectId, không phải JSON bình thường được lưu nguyên xi như _id object.

### 44.2. Giữ mapping một-một

Nếu hai ObjectIds cùng được cấp một publicId do bug, API có thể trỏ sai. Backfill phải kiểm tra unique constraints và duplicate resolution trước cutover.

### 44.3. Không đổi _id type tùy tiện

Trong MongoDB, _id của một document là immutable. Chuyển _id từ ObjectId sang String/UUID thường cần tạo record mới hoặc migration strategy phù hợp, cập nhật references và bảo đảm không có hai copies cùng được coi authoritative.

### 44.4. ID và shard placement

Đổi ID có thể đổi distribution/index/sort semantics. Một UUID text có kích thước và locality khác ObjectId; benchmark theo access patterns.

## 45. Migration số tiền: Double → Decimal128 hoặc minor units

Một hệ đang có:

~~~text
amount: BSON Double
~~~

muốn chuyển:

~~~text
amountDecimal: BSON Decimal128
currency: String
schemaVersion: 2
~~~

### 45.1. Tìm nguồn dữ liệu chính xác

Nếu có payment provider ledger hoặc hóa đơn gốc với số chính xác, ưu tiên đối soát từ nguồn có thẩm quyền thay vì xem Double là số gốc không sai.

### 45.2. Chọn rounding policy

Ví dụ khi dữ liệu cũ không thể khôi phục hoàn toàn:

- Gắn cờ legacyConversion.
- Ghi sourceOriginal/nguồn provenance theo policy.
- Dùng business-approved rounding.
- Đối soát totals và phát hiện chênh lệch.

### 45.3. Dual fields tạm thời

Có thể đọc amountDecimal nếu có, fallback legacy amount cho records chưa backfill. Đặt thời hạn migration rõ; không giữ hai trường có authority khác nhau mãi mãi.

### 45.4. Queries và index

Một filter amount > 100 trên field trộn BSON Double/Decimal128 có thể mang semantics khó kiểm soát. Chọn field mới, reindex/rewrite queries và kiểm chứng precision trước cutover.

## 46. Migration thời gian: String hoặc seconds → milliseconds UTC

Nguồn cũ:

~~~text
created_at = "2026-11-14 15:30:00"
timezone không được lưu
~~~

Đích muốn:

~~~text
createdAtEpochMs = ...
~~~

### 46.1. Không thể suy timezone khi thiếu

Nếu dữ liệu lịch sử không ghi zone/offset, không thể biết chắc chuỗi cũ là giờ server UTC, Hà Nội hay Region khác. Cần tìm evidence từ logs, deployment config và business records; phần không chắc chắn phải được đánh dấu.

### 46.2. Phân biệt epoch units

Một field chứa giây kể từ epoch sẽ nhỏ hơn milliseconds khoảng 1.000 lần. Không đoán chỉ bằng độ dài con số nếu có dates rất xa; dùng schema/source contract.

### 46.3. Backfill theo batch

Chia records theo key/range, ghi schemaVersion mới, checkpoint tiến độ, kiểm tra source consistency và replay mutations phát sinh trong quá trình backfill.

### 46.4. Cẩn thận với TTL

Nếu đổi expiresAt từ epoch millis sang epoch seconds mà một job chưa cập nhật, dữ liệu có thể bị xóa sớm/muộn bất thường. Thay đổi temporal schema cần xử lý tất cả consumers.

## 47. Schema validation và business validation khác nhau

### 47.1. Structural validation

Kiểm tra:

- id không null, đúng format.
- amount đúng decimal representation và range.
- createdAt hợp lệ, đúng precision.
- shipping.address.country đúng kiểu String.
- items là List và có phần tử đúng schema.

### 47.2. Business validation

Kiểm tra:

- Amount không âm nếu domain không cho phép refund dưới dạng âm.
- Currency được hỗ trợ.
- Quantity > 0.
- Reservation chưa hết hạn.
- Tenant/user có quyền.
- Một Order không nhận duplicate lineId trái invariant.

### 47.3. Data validation ở nhiều tầng

- API boundary chặn input sai sớm.
- Domain model bảo vệ invariants.
- Repository converter bảo vệ storage types.
- Database constraints/conditional writes bảo vệ concurrency trong phạm vi engine.

Không chỉ dựa vào annotations ở REST, vì background consumers và migrations có thể ghi qua đường khác.

### 47.4. Validate nested payload size

Input gồm map 100.000 keys hoặc list 1 triệu nested items có thể làm request tốn RAM/CPU và vượt item limit. Cần limits cho array size, map keys, depth và tổng payload bytes.

## 48. Index và query phụ thuộc đúng kiểu được lưu

### 48.1. ID type mismatch

MongoDB _id là ObjectId nhưng query String cùng hex → không match record như mong đợi.

### 48.2. Numeric type và sort

Lưu price dạng String có thể sort lexicographically thay vì numerically. Nếu buộc lưu decimal String, định nghĩa cách query/sort hoặc lưu numeric field bổ sung đã kiểm chứng.

### 48.3. Time string và sort

Chuỗi UTC không fixed-width fractional seconds có thể sort sai theo byte. Lưu BSON DateTime/epoch numeric hoặc ISO fixed-width chuẩn.

### 48.4. Nested path index

MongoDB index trên shipping.address.city hoặc các subfields khác giúp query phù hợp, nhưng arrays và multikey indexes có semantics riêng; cần chọn theo query thực tế.

### 48.5. DynamoDB access pattern

Một Map lồng nhau không thay thế thiết kế PK/SK và GSI. Dữ liệu nested có thể được update/filtered trong những API nhất định, nhưng DynamoDB query hiệu quả cần partition key thích hợp.

### 48.6. Cassandra primary key

UDT, list và map không thay partition/clustering key. Nếu query chủ yếu theo customerId+date, cần mô hình bảng theo access pattern; không trông đợi scan nested fields như relational JOIN mặc định.

## 49. Checklist trước khi phát hành mapper mới

### 49.1. Định danh

- ObjectId/String/UUID representation được ghi rõ chưa?
- Business ID có giữ leading zeros không?
- API ID có opaque và stable không?
- Tenant scope và uniqueness đúng không?
- Retry dùng stable operationId chưa?

### 49.2. Số chính xác

- Tiền còn bị chuyển qua double ở đâu không?
- Decimal128/DynamoDB Number có đủ precision/range không?
- Amount có currency/minor units/scale rõ không?
- Rounding policy và overflow được kiểm soát chưa?
- JSON consumers có thể parse large numbers an toàn không?

### 49.3. Ngày giờ

- CreatedAt là Instant hay LocalDateTime?
- Business date có bị ép thành UTC midnight sai không?
- Epoch seconds vs milliseconds đã đặt tên field rõ?
- Storage có mất micro/nano precision không?
- Local recurring events có zoneId và DST policy không?

### 49.4. Nested data

- Missing/null/empty có semantics rõ?
- PATCH giữ hay xóa field khi không có input?
- Nested arrays có limits và stable IDs?
- Mapper có xử lý legacy schema version?
- Partial update có bảo vệ concurrent writes?

### 49.5. Vận hành

- Có metrics type-conversion failures/legacy reads không?
- Có kế hoạch rollback khi schema migration gây lỗi?
- Consumer và indexer đã hiểu representation mới chưa?
- Có data lineage và chính sách xóa PII không?

## 50. Bài tập 1 — ObjectId và String ID

MongoDB có:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011"), customerId:"U101" }
~~~

Ứng dụng nhận URL:

~~~text
GET /customers/507f1f77bcf86cd799439011
~~~

Hãy:

1. Giải thích vì sao query _id với String có thể không tìm thấy record.
2. Viết đoạn Java parse ObjectId có kiểm tra isValid.
3. Đề xuất public API DTO không để mọi consumer phụ thuộc BSON.
4. Giải thích vì sao hex String không là quyền truy cập; vẫn cần authorization.
5. Nếu dữ liệu legacy có _id String và ObjectId, đề xuất adapter/migration.

## 51. Bài tập 2 — UUID representation

Một hệ MongoDB cũ lưu UUID theo binary legacy representation, service Java mới chuyển sang STANDARD.

1. UUID.toString() của hai sides có thể giống nhưng truy vấn binary lại khác không?
2. Cần inventory/configuration nào trước khi đổi driver UUID representation?
3. Có nên đổi tất cả UUID sang String ngay trong một release không?
4. Thiết kế migration có shadow reads và kiểm tra số record không match.
5. Phân biệt UUID v4 với timeuuid về khả năng sắp theo thời gian.

## 52. Bài tập 3 — giữ leading zeros

Các giá trị:

~~~text
customerCode = "00000123"
postalCode   = "00120"
phone        = "+84901234567"
invoiceNo    = "INV-000045"
~~~

1. Trường nào nên là String?
2. Nếu chuyển postalCode sang int rồi lưu lại, mất thông tin gì?
3. Nếu JSON consumer parse customerCode như Number, còn khôi phục nguyên trạng được không?
4. Vì sao những ID này không nên dùng double?
5. Đề xuất validators cho format và namespace.

## 53. Bài tập 4 — BigDecimal và binary floating point

Code:

~~~java
double a = 0.1;
double b = 0.2;
BigDecimal x = new BigDecimal(0.1);
BigDecimal y = new BigDecimal("0.1");
~~~

Hãy:

1. Dự đoán kết quả a+b khi in ra.
2. Giải thích sự khác nhau giữa x và y.
3. Viết phép cộng 0.1+0.2 bằng BigDecimal.
4. Chỉ ra vì sao serialize BigDecimal thành JSON number rồi parse qua JavaScript Number có thể mất precision.
5. Đề xuất contract amount decimal string cho API nhiều ngôn ngữ.

## 54. Bài tập 5 — scale và equality

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");
~~~

1. a.equals(b) trả gì?
2. a.compareTo(b) trả gì?
3. Nếu a và b làm keys trong HashSet, điều gì cần lưu ý?
4. Viết validation chấp nhận chính xác scale 2 mà không làm tròn.
5. Nếu currency có 0 fraction digits, policy thay đổi thế nào?

## 55. Bài tập 6 — tiền theo minor units

Một service nhận:

~~~text
amount = 123.45 USD
~~~

1. Chuyển sang amountMinor theo contract USD=2 fraction digits.
2. Viết Java BigDecimal.movePointRight kết hợp longValueExact.
3. Nếu amount=123.456, RoundingMode.UNNECESSARY cho biết gì?
4. Nếu amount vượt signed long, cách phát hiện?
5. Nếu amountMinor là số nguyên vượt miền an toàn của JS Number, API nên biểu diễn thế nào?
6. Vì sao không hardcode scale=2 cho mọi currency?

## 56. Bài tập 7 — BSON Decimal128

Một collection MongoDB gồm:

~~~text
Payment A amount = BSON Double
Payment B amount = BSON Decimal128
~~~

1. Java typed getter dùng Decimal128 có đọc A trực tiếp được không?
2. Vì sao chuyển Double sang BigDecimal không khôi phục chắc chắn giá trị thập phân gốc?
3. Viết code ghi một BigDecimal thành new Decimal128(amount).
4. Nêu giới hạn 34 chữ số có nghĩa.
5. Đề xuất migration có nguồn đối soát payment ledger và flag legacyConversion.

## 57. Bài tập 8 — DynamoDB Number và Map

Một AttributeValue:

~~~text
PK: S("ORDER#O101")
total: N("12345678901234567890.12")
address: M(
  country: S("VN")
  postalCode: S("700000")
)
~~~

1. Dùng BigDecimal.parse theo cách Java tương đương để đọc total (gợi ý: new BigDecimal(raw.n())).
2. Vì sao Double.parseDouble làm thay đổi yêu cầu exactness?
3. Sự khác biệt giữa S("700000") và N("700000") cho postalCode?
4. Viết code đọc city từ map nếu field optional.
5. Phân biệt M, L và SS khi biểu diễn order items.

## 58. Bài tập 9 — Cassandra decimal và timestamp

Một bảng:

~~~sql
CREATE TABLE payment_by_id (
  tenant_id text,
  payment_id uuid,
  amount decimal,
  captured_at timestamp,
  PRIMARY KEY ((tenant_id, payment_id))
);
~~~

1. Chọn Java types phù hợp cho bốn cột.
2. Vì sao Java BigDecimal và Instant phù hợp hơn double/LocalDateTime?
3. Captured_at trong CQL lưu precision tới mức nào theo kiểu timestamp?
4. Nếu hệ yêu cầu nano exact, schema có đáp ứng trực tiếp không?
5. UUID v4 có tự sắp xếp payment theo created time không?

## 59. Bài tập 10 — Instant và LocalDate

Một người sinh ngày 1998-03-05 ở múi giờ UTC-08:00. Hệ lưu birthday bằng DateTime 1998-03-05T00:00:00Z.

1. Khi hiển thị tại UTC-08:00, ngày có thể thành ngày nào?
2. Vì sao ngày sinh nên được mô hình LocalDate?
3. Ngược lại, payment capturedAt nên dùng LocalDate hay Instant?
4. Nếu một client gửi createdAt không có offset, cần contract gì?
5. Cho ví dụ lưu business expiry date và businessZone.

## 60. Bài tập 11 — DST và ngày kinh doanh

Một hệ đặt lịch tại Europe/Paris vào ngày chuyển DST.

1. Vì sao local 02:30 có thể không tồn tại hoặc xuất hiện hai lần tùy ngày?
2. Vì sao một OffsetDateTime với offset hiện tại không đủ cho lịch lặp trong tương lai?
3. Chọn LocalDateTime+ZoneId hay Instant cho giờ người dùng hẹn trước?
4. Viết hai Instant start/end cho một LocalDate trong ZoneId của cửa hàng.
5. Vì sao query timestamp bằng khoảng [start,end) tốt hơn đến 23:59:59.999?

## 61. Bài tập 12 — DynamoDB timestamp sort key

Hai chuỗi:

~~~text
2026-11-14T08:30:00Z
2026-11-14T08:30:00.001Z
~~~

1. Khi so byte theo thứ tự từ điển, chuỗi nào có thể đứng trước?
2. Thứ tự đó có khớp thời gian thực không?
3. Viết một DateTimeFormatter có fractional width cố định ba chữ số và UTC.
4. Nếu dữ liệu hiện tại trộn offsets +07:00 và Z, cần migration/normalization như thế nào?
5. Chọn ISO String hay epoch numeric cho sort/range theo workload?

## 62. Bài tập 13 — epoch seconds và milliseconds

Một job lưu expiresAt bằng Instant.toEpochMilli(), nhưng DynamoDB TTL xem attribute đó là epoch seconds.

1. Độ lớn hai đơn vị khác nhau bao nhiêu lần?
2. Hậu quả đối với TTL?
3. Viết converter đúng với Instant.getEpochSecond().
4. Tại sao TTL deletion không nên được dùng làm tín hiệu nghiệp vụ xóa ngay tức thời?
5. Nên đặt tên createdAtEpochMs và expiresAtEpochSeconds như thế nào để giảm lỗi?

## 63. Bài tập 14 — nested object và partial update

Document hiện có:

~~~json
{
  "_id": "O101",
  "shipping": {
    "recipient": "An",
    "address": {
      "city": "Hồ Chí Minh",
      "country": "VN",
      "postalCode": "700000"
    }
  }
}
~~~

Client chỉ muốn đổi city thành Đà Nẵng.

1. Vì sao thay toàn bộ shipping bằng object chỉ có city làm mất dữ liệu?
2. Viết MongoDB Updates.set cho shipping.address.city.
3. Nếu hai writers thay country và city dựa trên snapshots cũ, rủi ro lost update là gì?
4. Đề xuất version/CAS hoặc atomic nested path updates.
5. Có nên tự dùng địa chỉ mới trong Customer.profile để overwrite snapshot địa chỉ lịch sử Order không?

## 64. Bài tập 15 — null, missing và PATCH

Ba request JSON:

~~~json
{}
~~~

~~~json
{"phone": null}
~~~

~~~json
{"phone": ""}
~~~

1. Đề xuất semantics cho missing, explicit null, empty string.
2. Vì sao Java String phone=null có thể không phân biệt hai trường hợp đầu?
3. Thiết kế tri-state PatchValue hoặc JsonNode presence handling.
4. Khi update MongoDB, dùng $unset hay $set null trong tình huống nào?
5. Nếu API cũ không phân biệt missing/null, thay đổi hợp đồng cần compatibility plan gì?

## 65. Bài tập 16 — dữ liệu lồng nhau trong Cassandra

Một application dùng CQL UDT shipping_address và frozen<shipping_address> trong order row.

1. Frozen UDT ảnh hưởng partial field update thế nào?
2. Nếu address object ngày càng nhiều fields, cần version/schema planning ra sao?
3. Vì sao không lưu toàn bộ order history events trong một list khổng lồ?
4. Khi user muốn tìm orders theo city, cần dựa vào access pattern nào?
5. Khi chuyển address sang separate table, rủi ro về business snapshot và consistency là gì?

## 66. Bài tập 17 — full round-trip mapping

Thiết kế một Java Order aggregate với:

~~~text
orderId: UUID
tenantId: String
total: Money(BigDecimal + currency)
createdAt: Instant
expectedDeliveryDate: LocalDate
shipping: Address
items: List<OrderLine>
metadata: Map<String,String>
schemaVersion: int
~~~

Yêu cầu:

1. Chọn storage schema trên MongoDB hoặc DynamoDB.
2. Viết mapper từ domain sang storage representation.
3. Viết mapper ngược, kiểm tra null/missing/legacy types.
4. Định nghĩa timezone/precision và scale/rounding.
5. Định nghĩa String/binary UUID representation nhất quán.
6. Thiết kế test round-trip từ object gốc qua serialization và deserialize.
7. Đề xuất bài test cho Unicode, amount lớn, nanoseconds và nested empty lists.

## 67. Bài tập 18 — migration đa kiểu dữ liệu

Một hệ legacy có:

~~~text
_id: String mang ObjectId hex
amount: BSON Double
createdAt: String không có timezone
shippingAddress: JSON string
~~~

Hệ mới muốn:

~~~text
_id: ObjectId hoặc publicId UUID theo quyết định
amount: Decimal128
createdAt: BSON DateTime UTC
shippingAddress: embedded BSON Document
schemaVersion: 2
~~~

1. Với mỗi field, những thông tin nào có thể đã mất không khôi phục được?
2. Những nguồn đối soát nào cần dùng trước migration?
3. Thiết kế read-old/write-new với backfill checkpoint.
4. Giải thích vì sao không thể sửa _id MongoDB in-place tùy ý.
5. Nếu có search/cache references theo ID cũ, làm sao cutover không mất lookup?
6. Nếu createdAt legacy thiếu timezone, ứng dụng phải đánh dấu uncertainty như thế nào?
7. Khi rollback, dữ liệu mới ghi bằng schema v2 được xử lý ra sao?

## 68. Bài tập 19 — concurrency và idempotency

Client tạo Order, server cấp ObjectId rồi commit, nhưng response bị mất. Client retry với một request mới.

1. Unique ObjectId có ngăn hai orders được tạo không?
2. Stable operationId/idempotency key nên sinh ở đâu?
3. Tại sao không dùng timestamp làm unique claim?
4. Nếu domain orderId là UUID sinh ở client trước request, ưu/nhược điểm là gì?
5. Nếu Order có nested items và totalMinor, cần kiểm tra invariant total như thế nào khi nhiều retries diễn ra?

## 69. Bài tập 20 — xây bảng kiểm thử serialization

Hãy tạo bảng test input → storage → expected readback cho:

| Nhóm | Input gợi ý | Điều cần kiểm chứng |
|---|---|---|
| ID | ObjectId hex và String cùng nội dung | Không nhầm BSON types |
| UUID | Binary legacy vs STANDARD | Đọc đúng representation |
| BigDecimal | 1.0 và 1.00 | Numeric equality/scale |
| Decimal128 | 34/35 chữ số có nghĩa | Range và rejection |
| Minor units | Giá trị sát giới hạn long | Overflow |
| LocalDate | 1998-03-05 | Không lệch ngày khi hiển thị |
| Instant | Có nanoseconds | Storage precision loss có chủ đích |
| Timezone | DST gap/overlap | Conflict policy |
| JSON | Missing/null/empty | Giữ semantics |
| Nested | Map/List có Unicode | Round-trip đúng cấu trúc |
| PATCH | Chỉ sửa một field | Không xóa sibling fields |
| Migration | Record v1/v2 | Reader nhận đúng schema |

Không chỉ kiểm tra deserialize không ném exception. Đối với từng trường hợp, so **giá trị và ý nghĩa nghiệp vụ** đã được xác định.

## 70. Tổng kết

Ánh xạ dữ liệu Java với NoSQL không chỉ là đổi một Java object sang BSON, JSON hoặc AttributeValue. **Quyết định lưu kiểu gì sẽ ảnh hưởng trực tiếp tới tính đúng đắn, khả năng query, cập nhật, migration và phục hồi.**

Những nguyên tắc quan trọng:

1. **Định danh phải có contract.** ObjectId khác String; UUID binary có representation; business code và postal code cần giữ leading zeros; tenant scope/compound key quyết định uniqueness.
2. **Không dùng double cho số tiền exact.** Dùng BigDecimal, Decimal128, decimal hoặc minor units với chính sách currency, scale, rounding và overflow được xác định.
3. **Kiểm tra giới hạn storage.** BigDecimal Java không tự có nghĩa BSON Decimal128 hoặc DynamoDB Number chứa được mọi giá trị.
4. **Phân biệt các kiểu thời gian.** Instant cho một thời điểm, LocalDate cho ngày lịch, LocalDateTime+ZoneId cho lịch địa phương tương lai và DST.
5. **Timezone và precision phải rõ.** BSON DateTime/CQL timestamp thường giữ milliseconds; epoch seconds khác milliseconds; string sort key cần UTC và format cố định.
6. **Dữ liệu nested cần semantics.** Embedded object khác reference; List khác Set; missing, null, empty object và empty list không giống nhau.
7. **Partial updates phải an toàn.** Đừng replace cả nested object chỉ để thay một field nếu có thể làm mất siblings hoặc update đồng thời.
8. **Mapper không là validation duy nhất.** API, domain, repository và storage boundaries đều cần bảo vệ dữ liệu đúng kiểu/đơn vị và invariant.
9. **Schema evolution là bình thường ở NoSQL.** Readers cần biết versions cũ; migration số/ID/thời gian cần provenance, checkpoint, đối soát và kế hoạch cutover.
10. **Round-trip phải giữ ý nghĩa, không chỉ compile.** Đọc lại chính xác ID, money, timestamp, nested values và retry semantics theo hợp đồng.
11. **Driver và framework có converters riêng.** Jackson, MongoDB codec, DynamoDB Enhanced Client và CQL driver không mặc định xử lý mọi Java type giống nhau.
12. **Một value object hữu ích nhưng không thay business logic.** Money, CustomerId, Address và Instant giúp code rõ hơn; authorization, idempotency và transaction vẫn phải thiết kế ở đúng cấp.

Khi chuẩn bị đưa một Java model vào NoSQL, hãy tự hỏi:

> **“Tôi đã xác định rõ từng trường là định danh, đại lượng chính xác, ngày theo lịch, thời điểm tuyệt đối hay cấu trúc lồng nhau chưa; nếu ghi rồi đọc lại qua mọi driver, JSON API, cache và migration, giá trị có còn giữ đúng ý nghĩa ban đầu không?”**





