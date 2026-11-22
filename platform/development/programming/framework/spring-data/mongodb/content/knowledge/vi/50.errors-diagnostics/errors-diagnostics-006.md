# Sai kiểu số, UUID hoặc thời gian giữa Java và BSON

Trong **Spring Data MongoDB**, việc ghi hoặc đọc một document đi qua nhiều lớp: kiểu Java của entity, **MappingMongoConverter**, MongoDB Java Driver/BSON codec và kiểu BSON thật sự nằm trong collection. Một trường tên **amount** có thể là **String** trong document cũ, **Decimal128** trong document mới; một trường **customerId** có thể là UUID dạng binary subtype 3, subtype 4 hoặc chuỗi; một trường **createdAt** có thể là BSON Date hoặc văn bản ISO 8601. Chỉ nhìn giá trị hiển thị trong JSON thường không đủ để phân biệt.

Các sai lệch này có thể gây lỗi chuyển đổi khi đọc, sai lệch độ chính xác, mất kết quả truy vấn, hoặc dịch thời gian ngoài dự kiến. Bài trong chương **Lỗi và chẩn đoán** tập trung vào cách xác minh **kiểu thật của BSON**, đối chiếu với mô hình Java và sửa nguyên nhân trong ứng dụng dùng **MongoTemplate**, **MongoRepository**, aggregation hoặc reactive access.

## 1. Mục tiêu và mô hình chẩn đoán

Sau bài này, bạn có thể:

1. Phân biệt **BSON int32, int64, double, Decimal128, string** và chọn kiểu Java phù hợp.
2. Chẩn đoán UUID **STANDARD/subtype 4**, UUID **legacy/subtype 3** và UUID lưu dưới dạng chuỗi.
3. Giải thích sự khác nhau giữa **Instant, LocalDateTime, OffsetDateTime, ZonedDateTime**, BSON Date và BSON Timestamp.
4. Kiểm tra dữ liệu gốc bằng **mongosh**, **$type** và **RawBsonDocument** trước khi thay đổi converter.
5. Thiết kế kiểm thử **round-trip** và quy trình sửa dữ liệu cũ an toàn, có thể chạy lại.

~~~mermaid
flowchart TD
    A["Lỗi đọc / ghi / truy vấn MongoDB"] --> B["Xác nhận field, _id và document lỗi"]
    B --> C["Đọc BSON gốc: $type, raw document, binary subtype"]
    C --> D["Đối chiếu kiểu entity và MappingMongoConverter"]
    D --> E["Đối chiếu cấu hình Java Driver và version"]
    E --> F{"Sai kiểu nào?"}
    F -- "Số" --> G["Precision / range / Decimal128 / String"]
    F -- "UUID" --> H["Subtype 3/4 / byte order / representation"]
    F -- "Thời gian" --> I["BSON Date / epoch ms / múi giờ"]
    G --> J["Sửa mapping hoặc migration có kiểm soát"]
    H --> J
    I --> J
    J --> K["Test round-trip + query + dữ liệu cũ"]
~~~

**Nguyên tắc đầu tiên:** đừng thử ép kiểu Java hoặc đổi cấu hình toàn hệ thống ngay khi thấy lỗi. Hãy xác nhận có bao nhiêu document sai schema, chúng được ghi bởi phiên bản ứng dụng nào và BSON thực tế là gì. Cấu hình “đọc được một document” có thể khiến những document khác bị giải mã sai.

## 2. Nhận diện triệu chứng trước khi sửa

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xác minh nhanh |
| --- | --- | --- |
| Đọc **amount** thành **BigDecimal** thất bại | Dữ liệu là string không hợp lệ, double, hoặc converter không phù hợp | **$type**, raw BSON, quy tắc **BigDecimalRepresentation** |
| Tổng tiền hoặc số đếm sai sau xử lý | Double bị làm tròn, tràn int32/int64, chuyển đổi có mất mát | Kiểu gốc, giá trị lớn, ranh giới và phép toán Java |
| **findByCustomerId(UUID)** không trả kết quả | UUID lưu subtype 3 nhưng query dùng subtype 4, hoặc lưu string | Đọc **binary subtype** và cấu hình **UuidRepresentation** |
| Driver báo lỗi codec UUID | UUID representation chưa được chọn, hoặc byte order legacy không phù hợp | Cấu hình MongoClientSettings/connection URI |
| Thời điểm đọc lệch 7 giờ | LocalDateTime bị hiểu theo UTC hoặc múi giờ máy chạy | BSON Date UTC, JVM default zone, converter đang dùng |
| Cùng bản ghi nhưng mất phần nano giây | BSON Date chỉ lưu **mili giây** | So sánh **Instant** trước và sau round-trip |
| Lọc theo ngày không thấy dữ liệu | Query dùng string thay vì BSON Date, hoặc sai biên múi giờ | Kiểu dữ liệu và **[start, end)** theo vùng thời gian nghiệp vụ |
| TTL index không xóa document | Trường thời gian đang là string, long, hoặc cấu hình TTL chưa đúng | **$type** của field và định nghĩa index |

Tên exception cụ thể thay đổi theo driver, converter và đường thao tác. Có thể gặp **MappingException**, **ConversionFailedException**, **CodecConfigurationException**, lỗi driver hoặc không có exception nhưng kết quả query rỗng. Vì vậy hãy giữ **message, nested cause, field, version và loại BSON** trong log chẩn đoán, tránh kết luận chỉ từ tên exception.

## 3. Các kiểu số: Java và BSON không tương đương một-một

MongoDB có nhiều kiểu numeric với giới hạn khác nhau:

| BSON | Alias của **$type** | Java thường dùng | Rủi ro |
| --- | --- | --- | --- |
| **Int32** | **int** | **int / Integer** | Chỉ chứa giá trị từ -2³¹ đến 2³¹ − 1 |
| **Int64** | **long** | **long / Long** | Giới hạn ±2⁶³, cần xử lý overflow |
| **Double** | **double** | **double / Double** | IEEE 754; nhiều giá trị thập phân không biểu diễn chính xác |
| **Decimal128** | **decimal** | **BigDecimal** hoặc **Decimal128** | Tối đa 34 chữ số có nghĩa và giới hạn exponent; không phải mọi BigDecimal đều biểu diễn được |
| **String** | **string** | **String** | Không phải numeric; so sánh chuỗi và so sánh số khác nhau |

**Ví dụ:** cùng giá trị hiển thị **12.30**, các document có thể lưu:

~~~javascript
db.payments.insertMany([
  { _id: "n-int",    amount: NumberInt("12") },
  { _id: "n-long",   amount: NumberLong("12") },
  { _id: "n-double", amount: 12.30 },
  { _id: "n-dec",    amount: NumberDecimal("12.30") },
  { _id: "n-string", amount: "12.30" }
]);
~~~

Trong **mongosh**, dùng constructor **NumberInt**, **NumberLong** và **NumberDecimal** để kiểm soát kiểu; đừng chỉ nhìn kết quả in thành JSON thông thường. **Extended JSON Canonical** giữ các type marker như **$numberInt**, **$numberLong**, **$numberDouble**, **$numberDecimal** rõ ràng hơn JSON dạng relaxed.

### 3.1. Quan hệ giữa các kiểu số khi truy vấn

MongoDB **xem các kiểu numeric tương đương cho nhiều phép so sánh số**: ví dụ, điều kiện so sánh với 12 có thể khớp giá trị ở cả int32, int64, double hoặc decimal nếu chúng có cùng giá trị số. Vì vậy không nên khẳng định mọi truy vấn từ **Long** sẽ hoàn toàn không tìm thấy **Int32**.

Tuy nhiên, điều kiện so sánh giữa **numeric** và **String** chịu quy tắc phân biệt loại BSON; truy vấn số **không tự hiểu** chuỗi "12.30" là Decimal128. Kết quả còn chịu ảnh hưởng độ chính xác của Double và cách driver/mapping converter tạo giá trị BSON trong query.

~~~javascript
// Chỉ kiểm tra document có BSON kiểu số.
db.payments.find({ amount: { $type: "number" } });

// Chỉ kiểm tra document có kiểu decimal128.
db.payments.find({ amount: { $type: "decimal" } });

// Kiểm tra riêng dữ liệu được lưu dưới dạng chuỗi.
db.payments.find({ amount: { $type: "string" } });
~~~

Khi tính tổng bằng aggregation, nên xác định kiểu đầu vào và kiểu đầu ra. Việc trộn **double**, **decimal**, **long** và dữ liệu string có thể tạo hành vi không mong muốn ở ranh giới chuyển đổi; phải kiểm thử giá trị biên và quy tắc làm tròn của nghiệp vụ.

### 3.2. BigDecimal, Decimal128 và cấu hình Spring Data

**BigDecimal** là kiểu số thập phân Java với precision rất rộng, còn **Decimal128** là kiểu BSON có giới hạn. Trước đây, nhiều phiên bản Spring Data MongoDB mặc định lưu BigDecimal ở dạng **String**; từ **Spring Data MongoDB 5.0**, việc chọn biểu diễn mặc định cần được cấu hình một cách tường minh. Không đoán hành vi hiện tại chỉ từ kiểu field Java.

Một lựa chọn cho trường tiền là lưu theo **Decimal128**:

~~~java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("invoices")
public class Invoice {
    @Id
    private String id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    protected Invoice() {}

    public Invoice(String id, BigDecimal amount) {
        this.id = id;
        this.amount = amount;
    }

    public String getId() { return id; }
    public BigDecimal getAmount() { return amount; }
}
~~~

Trong một ứng dụng dùng nhiều trường **BigDecimal**, hãy xem **MongoCustomConversions** và thiết lập **BigDecimalRepresentation** theo phiên bản Spring Data để bảo đảm kiểu lưu mặc định là lựa chọn có chủ đích. **@Field(targetType = FieldType.DECIMAL128)** cho phép khai báo biểu diễn BSON của thuộc tính cụ thể. Kiểm tra dữ liệu đã ghi, không chỉ kiểm tra annotation.

Với tiền tệ, hai chiến lược thường gặp là:

- **Decimal128** nếu cần phép tính/truy vấn thập phân trên MongoDB và giá trị nằm trong giới hạn precision/exponent.
- **Long số đơn vị nhỏ nhất** (ví dụ số cent) nếu đơn vị nghiệp vụ cố định; cần kiểm soát scale và tràn số khi nhân/chia.

**Double** không phù hợp khi ứng dụng yêu cầu biểu diễn thập phân chính xác cho các phép đối soát tài chính. Cũng không nên chuyển BigDecimal thành Double bằng **doubleValue()** rồi mong chờ bảo toàn từng chữ số.

Đặc biệt, **BigDecimal.equals** xét cả **scale**, còn **compareTo** so sánh giá trị số:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("12.3");

assert !a.equals(b);       // scale khác nhau
assert a.compareTo(b) == 0; // giá trị số bằng nhau
~~~

Khi test round-trip, chọn kỳ vọng rõ ràng: **giá trị số** hay **scale hiển thị**. Nếu hệ thống yêu cầu scale cố định, quy định scale/rounding trước khi ghi và kiểm tra nó; MongoDB không tự thay bạn xác định quy tắc kế toán.

### 3.3. Tràn số và phép ép kiểu nguy hiểm

~~~java
long total = 3_000_000_000L;

// Có thể mất dữ liệu do ép kiểu hẹp:
int unsafe = (int) total;

// Ném ArithmeticException nếu không biểu diễn được:
int checked = Math.toIntExact(total);
~~~

**int**, **long**, **BigInteger** và **BigDecimal** là các contract khác nhau. Không sửa một lỗi mapping bằng cách đổi toàn bộ field sang **int** nếu dữ liệu có thể vượt giới hạn. Dùng **Math.addExact / multiplyExact / toIntExact** để phát hiện overflow ở logic Java khi cần; trong MongoDB, kiểm thử các giá trị biên khi dùng update/aggregation. Một converter âm thầm cắt phần lẻ hoặc ép int có thể khiến dữ liệu sai mà không có exception.

## 4. UUID: cùng giá trị hiển thị, khác BSON binary

**UUID Java** là 128-bit, nhưng MongoDB có nhiều representation lịch sử:

| Lưu trữ | BSON | Đặc điểm |
| --- | --- | --- |
| **STANDARD** | Binary subtype **4** | Định dạng khuyến nghị cho dữ liệu UUID mới |
| **JAVA_LEGACY** | Binary subtype **3** | Byte order tương thích dữ liệu do Java driver cũ ghi |
| **CSHARP_LEGACY / PYTHON_LEGACY** | Binary subtype **3** | Cũng subtype 3 nhưng cách sắp thứ tự byte có thể khác Java legacy |
| **Chuỗi UUID** | BSON **string** | Không cùng kiểu với Binary subtype 3 hoặc 4 |

Hai UUID trông giống nhau khi được hiển thị ở tầng ứng dụng vẫn có thể tạo BSON khác nhau. Khi query một UUID, driver cần **mã hóa lại tham số truy vấn theo representation phù hợp với dữ liệu đã lưu**; dùng subtype 4 để tìm document subtype 3 có thể không trả bản ghi.

### 4.1. Cấu hình UUID representation rõ ràng

Với MongoDB Java driver đồng bộ:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.UuidRepresentation;

public final class MongoClientFactory {
    public static MongoClient create(String connectionUri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(connectionUri))
            .uuidRepresentation(UuidRepresentation.STANDARD)
            .build();
        return MongoClients.create(settings);
    }
}
~~~

Với cấu hình auto-configuration của **Spring Boot** trên những phiên bản hỗ trợ thuộc tính tương ứng:

~~~properties
spring.data.mongodb.uuid-representation=standard
~~~

Nếu tự tạo **MongoClient** bean, phải xác minh **MongoTemplate**, repository và test đang dùng đúng client đã cấu hình; property trên có thể không tác động đến client được tạo hoàn toàn thủ công. Cũng cần kiểm tra driver cũ hoặc các dịch vụ viết khác có đang dùng **JAVA_LEGACY**.

**Không đổi toàn hệ thống sang STANDARD một cách mù quáng** khi đã có dữ liệu UUID legacy. Cấu hình mới ảnh hưởng đến việc serialize tham số query/ghi mới và decode dữ liệu; dữ liệu subtype 3 có thể không còn được đọc/truy vấn như trước. Để chuyển đổi an toàn cần xác minh nguồn gốc và byte order của **từng nhóm dữ liệu**, chuẩn hóa sang subtype 4, kiểm thử bằng UUID known-value và cập nhật đồng bộ các ứng dụng đọc/ghi.

### 4.2. Chẩn đoán UUID bằng raw BSON

Toán tử **$type** sẽ trả **binData** cho cả subtype 3 và 4, nên kiểm tra subtype bằng Java raw BSON hoặc Extended JSON với phần **$binary.subType**.

~~~javascript
// Kiểm tra dữ liệu lưu dạng binary hay string.
db.payments.aggregate([
  {
    $group: {
      _id: { $type: "$customerId" },
      count: { $sum: 1 }
    }
  }
]);

// Hiển thị một vài document trong mongosh.
db.payments.find({}, { customerId: 1 }).limit(5);
~~~

Để biết chắc binary subtype mà không dựa vào cách một client tự động chuyển UUID thành đối tượng Java, dùng **RawBsonDocument**:

~~~java
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class RawUuidProbe {
    public static void inspect(MongoTemplate template, String paymentId) {
        RawBsonDocument raw = template.getCollection("payments")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", paymentId))
            .first();

        if (raw == null) {
            throw new IllegalArgumentException("Document not found");
        }

        if (raw.containsKey("customerId")
                && raw.get("customerId").getBsonType() == BsonType.BINARY) {
            int subtype = Byte.toUnsignedInt(
                raw.getBinary("customerId").getType()
            );
            System.out.println("customerId subtype = " + subtype);
        } else {
            System.out.println("customerId is not BSON Binary");
        }
    }
}
~~~

Trong log sản xuất, ưu tiên ghi **loại BSON và subtype**, không in toàn bộ UUID/dữ liệu khách hàng khi không cần. **RawBsonDocument** là công cụ đọc raw BSON cho chẩn đoán; không có nghĩa ứng dụng nên bỏ mọi converter và xử lý bytes thủ công.

## 5. Thời gian: BSON Date, UTC, độ chính xác và múi giờ

**BSON Date** lưu **số mili giây** kể từ Unix epoch và biểu diễn một **thời điểm tuyệt đối**. Nó **không lưu kèm ZoneId, múi giờ nguồn hoặc offset người dùng**. Đừng nhầm với kiểu BSON **Timestamp** dành cho ngữ cảnh nội bộ MongoDB như oplog.

| Java / BSON | Ý nghĩa | Rủi ro thường gặp |
| --- | --- | --- |
| **java.time.Instant** | Một thời điểm trên dòng thời gian UTC | Mất phần precision nhỏ hơn mili giây khi lưu BSON Date |
| **java.util.Date** | Một thời điểm theo epoch milliseconds | Hiển thị có thể đổi theo timezone của formatter |
| **LocalDateTime** | Ngày-giờ địa phương **không có** múi giờ | Không xác định được instant nếu thiếu quy ước zone |
| **OffsetDateTime** | Ngày-giờ kèm offset | Muốn bảo toàn offset gốc cần lưu thêm thông tin; converter hỗ trợ tùy cấu hình |
| **ZonedDateTime** | Ngày-giờ kèm ZoneId và quy tắc vùng | Nếu chỉ lưu BSON Date sẽ mất ZoneId ban đầu |
| **BSON Date** | Epoch milliseconds, UTC datetime | Khác String ISO, Long epoch, BSON Timestamp |
| **BSON String** | Văn bản, ví dụ "2026-11-20T08:00:00Z" | Không tự được coi là Date trong filter/index TTL |

**Ví dụ múi giờ:** **2026-11-20 08:00 tại Asia/Ho_Chi_Minh** tương ứng **2026-11-20T01:00:00Z**. Nếu một chương trình vô tình hiểu 08:00 thành UTC, thời điểm sẽ bị lệch **7 giờ**.

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.of(2026, 11, 20, 8, 0);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
Instant correct = local.atZone(vietnam).toInstant();

assert correct.equals(Instant.parse("2026-11-20T01:00:00Z"));
~~~

### 5.1. Quy tắc codec của LocalDateTime cần kiểm chứng

Spring Data MongoDB có thể sử dụng **Spring Data JSR-310 converters** cho các kiểu local, hoặc **native Java Driver Java Time codecs** tùy phiên bản và cấu hình:

- Các converter Spring Data cho **LocalDateTime** có thể sử dụng **ZoneId.systemDefault()**.
- Native driver Java Time codecs được Spring Data cấu hình dùng **ZoneOffset.UTC** cho các kiểu local tương ứng.

Nếu môi trường phát triển chạy với timezone **Asia/Ho_Chi_Minh** nhưng CI/container chạy **UTC**, cùng một **LocalDateTime** có thể sinh BSON Date khác nhau trong một số cấu hình converter. Vì vậy trường biểu thị **thời điểm sự kiện** nên dùng **Instant** và quy ước UTC; dữ liệu biểu thị **giờ hẹn tại địa phương** cần lưu zone hoặc định nghĩa chuyển đổi rõ ràng.

**Không ép mọi dữ liệu thành UTC datetime nếu nghiệp vụ cần giữ giờ địa phương.** Ví dụ “mở cửa lúc 09:00 hằng ngày ở Hà Nội” là giờ theo lịch/vùng, không phải một Instant duy nhất.

### 5.2. Độ chính xác mili giây

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant before = Instant.parse("2026-11-20T01:02:03.123456789Z");
Instant expectedAfterBsonDate = before.truncatedTo(ChronoUnit.MILLIS);

assert expectedAfterBsonDate.equals(
    Instant.parse("2026-11-20T01:02:03.123Z")
);
~~~

BSON Date không lưu nanosecond riêng; nếu hệ thống yêu cầu microsecond/nanosecond, cần một quy ước khác (ví dụ trường bổ sung hoặc epoch microsecond dưới dạng Long) và test tương ứng. **Không** so sánh nguyên vẹn nanosecond từ Java Instant với round-trip của BSON Date rồi kết luận converter hỏng.

### 5.3. Truy vấn theo ngày: dùng khoảng nửa mở

Với câu hỏi “tìm giao dịch phát sinh trong ngày **20/11/2026** theo giờ Việt Nam”, hãy xác định mốc bắt đầu và kết thúc **ở múi giờ nghiệp vụ**, rồi đổi sang Instant:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 20);

Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();

Query q = Query.query(
    Criteria.where("paidAt")
        .gte(Date.from(from))
        .lt(Date.from(to))
);
~~~

Đoạn này minh họa phần thân phương thức query, không phải một file Java độc lập. Điều kiện **[from, to)** tránh cộng “23:59:59.999” một cách thủ công và chính xác khi ngày có đổi giờ mùa hè tại các vùng khác. Trong entity có field **Instant paidAt**, Spring Data cũng có thể ánh xạ tham số thời gian; dùng **Date.from** ở đây giúp chủ ý đưa một BSON Date vào query rõ ràng.

Đừng truyền chuỗi **"2026-11-20"** vào **Criteria.gte** trên trường BSON Date rồi kỳ vọng server tự parse. Tương tự, TTL index cần trường kiểu **BSON Date** (hoặc phần tử Date trong mảng theo quy định), chứ không hoạt động như ý với trường chứa ISO string.

## 6. Truy vấn bằng $type để kiểm kê dữ liệu thật

Trước khi sửa Java class, lập báo cáo tỷ lệ kiểu BSON trong collection. Ví dụ trên **payments**:

~~~javascript
db.payments.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      customerIdType: { $type: "$customerId" },
      paidAtType: { $type: "$paidAt" }
    }
  },
  {
    $group: {
      _id: {
        amount: "$amountType",
        customerId: "$customerIdType",
        paidAt: "$paidAtType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

**$type aggregation** có thể trả **"missing"** cho field không tồn tại; riêng giá trị **null** là **"null"**. **"binData"** không phân biệt subtype UUID, nên cần raw BSON hoặc Extended JSON canonical để phân tích sâu UUID.

Kiểm tra từng nhóm có vấn đề:

~~~javascript
db.payments.find(
  { amount: { $type: "string" } },
  { _id: 1, amount: 1 }
).limit(20);

db.payments.find(
  { paidAt: { $type: "string" } },
  { _id: 1, paidAt: 1 }
).limit(20);

db.payments.find(
  { customerId: { $type: "binData" } },
  { _id: 1, customerId: 1 }
).limit(20);
~~~

Chỉ lấy một số document đại diện và lưu thông tin định danh an toàn khi điều tra production. Khi có hàng triệu bản ghi, chạy aggregation kiểm kê trên cửa sổ tải phù hợp, theo dõi tài nguyên và xem **explain** nếu truy vấn tốn nhiều chi phí. Một truy vấn đếm theo **$type** vẫn phải đọc dữ liệu nếu không có kế hoạch index thích hợp.

### 6.1. Kiểm tra số có chuyển đổi được không

Với trường amount cũ dạng String, trước tiên thực hiện pipeline **đọc**, dùng **$convert** và **onError** để không làm hỏng dữ liệu:

~~~javascript
db.payments.aggregate([
  { $match: { amount: { $type: "string" } } },
  {
    $project: {
      amount: 1,
      candidate: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $match: { candidate: null } },
  { $limit: 20 }
]);
~~~

Đây là ví dụ liệt kê **chuỗi không chuyển đổi được thành Decimal128**; nó chưa ghi bất kỳ dữ liệu nào. **$convert** có thể chuyển một số giá trị BSON qua các loại khác nhau, nhưng conversion không giải quyết nghiệp vụ của giá trị bất thường. Chỉ cho phép chuyển những định dạng mà chủ sở hữu dữ liệu xác nhận (ví dụ decimal separator ".", không có ký hiệu tiền tệ, không có dữ liệu nhập sai).

## 7. Chẩn đoán raw BSON bằng MongoTemplate

Đôi khi giá trị đã được **MappingMongoConverter** biến thành một kiểu Java khác trước khi bạn nhìn thấy. Để kiểm tra loại BSON một cách độc lập với entity mapping, sử dụng **RawBsonDocument**:

~~~java
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public class PaymentBsonDiagnostics {
    public static void inspect(MongoTemplate template, String id) {
        RawBsonDocument raw = template.getCollection("payments")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", id))
            .first();

        if (raw == null) {
            throw new IllegalStateException("Payment not found");
        }

        for (String field : new String[]{"amount", "customerId", "paidAt"}) {
            if (!raw.containsKey(field)) {
                System.out.println(field + ": MISSING");
                continue;
            }
            BsonType type = raw.get(field).getBsonType();
            System.out.println(field + ": " + type);
            if (type == BsonType.BINARY) {
                int subtype = Byte.toUnsignedInt(
                    raw.getBinary(field).getType()
                );
                System.out.println("  subtype=" + subtype);
            }
        }
    }
}
~~~

Không giả định rằng **Document.toJson()** ở chế độ mặc định luôn cho biết sự khác nhau giữa Int32, Int64, Date hay subtype. Nếu cần xuất chẩn đoán chính xác, chọn **Extended JSON Canonical** hoặc **RawBsonDocument**. Mã chẩn đoán chỉ in kiểu/subtype; tránh log giá trị bí mật.

**Phân biệt ba lớp khi debug:**

| Lớp | Câu hỏi |
| --- | --- |
| MongoDB Server / BSON | Field đang có kiểu và subtype thật nào? Có nhiều kiểu xen kẽ không? |
| MongoDB Java Driver | Codec dùng UUID representation nào? Có thể đọc/ghi loại BSON đó không? |
| Spring Data mapping | Field khai báo Java gì? Có **@Field(targetType)**, converter tự tạo hoặc mapping property name khác không? |

Nếu lỗi xảy ra khi repository đọc một document, có thể tạm lấy raw document theo **_id** qua MongoTemplate để biết chính xác kiểu. Tránh viết một converter “nhận mọi thứ” trước khi phân loại dữ liệu; converter quá rộng có thể che dữ liệu bẩn hoặc làm mất precision.

## 8. Thiết kế entity và contract lưu trữ rõ ràng

Một ví dụ thống nhất cho collection **payments**:

~~~java
package example.payments;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("payments")
public class Payment {
    @Id
    private String id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private UUID customerId;
    private Instant paidAt;

    protected Payment() {}

    public Payment(
            String id, BigDecimal amount,
            UUID customerId, Instant paidAt) {
        this.id = id;
        this.amount = amount;
        this.customerId = customerId;
        this.paidAt = paidAt;
    }

    public String getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public UUID getCustomerId() { return customerId; }
    public Instant getPaidAt() { return paidAt; }
}
~~~

Contract của ví dụ:

- **amount:** Decimal128 theo định nghĩa mapping; ứng dụng kiểm tra precision/scale và điều kiện số hợp lệ trước khi lưu.
- **customerId:** BSON Binary subtype **4**, toàn bộ writer và reader dùng **UuidRepresentation.STANDARD**.
- **paidAt:** BSON Date biểu diễn **UTC instant**, độ chính xác milli giây; không dùng LocalDateTime để biểu diễn một thời điểm toàn cục.
- **_id:** String do ứng dụng định nghĩa, không trộn với UUID Binary hoặc ObjectId.

Không thay toàn bộ entity ở production ngay lập tức nếu collection đang chứa kiểu cũ: một số bản ghi có thể đọc thất bại sau khi deploy. Cần kế hoạch **expand–migrate–contract** hoặc converter tương thích có giới hạn trong thời gian chuyển đổi.

## 9. Kiểm thử round-trip và BSON type thật

Unit test của hàm chuẩn hóa, converter hay logic tiền tệ là cần thiết, nhưng không xác minh thực tế driver đã ghi **Decimal128**, UUID subtype 4 và BSON Date. Với những contract trên, hãy dùng **@DataMongoTest + MongoDB thật** để kiểm tra round-trip và raw BSON.

Ví dụ dành cho **Spring Boot 3.x / Spring Data MongoDB 4.x, Testcontainers 1.x**; thay package và cấu hình theo version thực của dự án nếu dùng major khác:

~~~java
package example.payments;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import com.mongodb.client.model.Filters;

@DataMongoTest(
    properties = "spring.data.mongodb.uuid-representation=standard"
)
@Testcontainers
class PaymentBsonContractTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @Test
    void mustPersistAmountUuidAndInstantUsingExpectedBsonTypes() {
        UUID customerId = UUID.fromString(
            "dcd8f7fe-8760-4fc3-a412-0f110da69911"
        );
        Instant paidAt = Instant.parse(
            "2026-11-20T01:02:03.123456789Z"
        );

        Payment sample = new Payment(
            "payment-type-contract-01",
            new BigDecimal("12.30"),
            customerId,
            paidAt
        );
        template.remove(
            org.springframework.data.mongodb.core.query.Query.query(
                org.springframework.data.mongodb.core.query.Criteria
                    .where("_id").is(sample.getId())
            ),
            Payment.class
        );
        template.insert(sample);

        RawBsonDocument raw = template.getCollection("payments")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", sample.getId()))
            .first();
        assertNotNull(raw);
        assertEquals(
            BsonType.DECIMAL128,
            raw.get("amount").getBsonType()
        );
        assertEquals(
            BsonType.BINARY,
            raw.get("customerId").getBsonType()
        );
        assertEquals(
            4,
            Byte.toUnsignedInt(raw.getBinary("customerId").getType())
        );
        assertEquals(
            BsonType.DATE_TIME,
            raw.get("paidAt").getBsonType()
        );

        Payment reloaded = template.findById(sample.getId(), Payment.class);
        assertNotNull(reloaded);
        assertEquals(0, sample.getAmount().compareTo(reloaded.getAmount()));
        assertEquals(customerId, reloaded.getCustomerId());
        assertEquals(
            paidAt.truncatedTo(ChronoUnit.MILLIS),
            reloaded.getPaidAt()
        );
    }
}
~~~

**Ý nghĩa của bài test:** nó chứng minh byte-level BSON type của dữ liệu thực tế và giá trị Java sau khi mapping ngược. Dùng **MongoDB version gần production**, kiểm tra lại cấu hình UUID của bean **MongoClient** và version Spring Data; nếu converter BigDecimal toàn cục thay đổi, bài test cần chỉ ra sự khác biệt sớm.

Với **ReactiveMongoTemplate**, nguyên tắc tương tự nhưng phải subscribe publisher và chờ hoàn tất, ví dụ qua **StepVerifier**. Một thao tác reactive chỉ được khai báo mà không subscribe có thể chưa hề ghi dữ liệu.

Nên bổ sung các test sau:

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Giá trị **BigDecimal("0.1")**, số âm và giá trị biên | Không chuyển qua Double gây sai precision |
| Số vượt khả năng Decimal128 | Lỗi rõ ràng, không lưu giá trị đã bị làm tròn trái chính sách |
| UUID chuẩn đã lưu | Query bằng **UUID Java** tìm đúng document |
| UUID legacy subtype 3 | Migration/compatibility path xử lý đúng theo byte order nguồn |
| BSON Date có nanos đầu vào | Round-trip khớp chính xác đến millisecond |
| Ngày theo múi giờ nghiệp vụ | Truy vấn **[start, end)** lấy đúng bản ghi đầu/cuối ngày |
| amount, customerId hoặc paidAt bị lưu string | Phát hiện dữ liệu sai contract; không âm thầm coi là hợp lệ |
| Thiếu field/null và dữ liệu lịch sử | Có chính sách default, reject hoặc migration nhất quán |

## 10. Sửa dữ liệu cũ: kiểm kê, thử nghiệm rồi migration

Quy trình an toàn cho một collection đang hoạt động:

1. **Chốt contract đích** cho từng field: BSON type, precision/scale, UUID representation, timezone và khả năng query/index.
2. **Kiểm kê trước** bằng **$type**, kiểm tra UUID subtype và đo số document thuộc mỗi nhóm.
3. **Phân loại dữ liệu không chuyển đổi được**; không đoán giá trị của amount bẩn hoặc thời gian thiếu zone.
4. **Viết và kiểm thử chương trình migration** trên bản sao dữ liệu; log kết quả từng lô và checkpoint để chạy lại an toàn.
5. **Dùng cập nhật có điều kiện** dựa trên kiểu/phiên bản hiện tại để không ghi đè dữ liệu vừa được ứng dụng thay đổi.
6. **Mở rộng khả năng đọc/ghi** hoặc triển khai chế độ tương thích trong giai đoạn chuyển tiếp, rồi mới thu hẹp schema khi hoàn tất đối soát.
7. **Đối soát sau** số lượng, các giá trị nghiệp vụ, query, index và test round-trip; chuẩn bị phương án khôi phục.

### 10.1. Với amount dạng String

Đối với những chuỗi đã được xác minh chỉ chứa số hợp lệ, MongoDB có thể dùng **$convert** trong update pipeline để đổi sang Decimal128. Trước khi ghi, chạy pipeline kiểm kê như phần 6.1 trên bản sao dữ liệu; kiểm tra precision, dữ liệu có dấu phân cách không đúng và hành vi của **onError/onNull**.

Không áp dụng đại trà **$toDecimal** mà bỏ qua lỗi chuyển đổi: một document không hợp lệ có thể làm thất bại lô. **$convert** với onError rõ ràng có thể dùng để lập danh sách lỗi hoặc để giữ lại giá trị cũ, nhưng không được âm thầm gắn status migration thành công cho document chưa chuyển đổi.

### 10.2. Với UUID legacy

Không có một biểu thức chuyển đổi universal từ **BinData subtype 3** sang subtype 4 mà vẫn đúng cho mọi writer. Phải biết dữ liệu gốc được ghi bằng **JAVA_LEGACY**, **CSHARP_LEGACY** hay **PYTHON_LEGACY** và dùng converter/codec thích hợp để phục hồi UUID logic trước khi ghi dạng STANDARD. Đặc biệt không thay trực tiếp byte subtype 3 thành subtype 4 khi chưa xét byte order.

Với nhiều ứng dụng cùng truy cập collection, lên lịch thay đổi reader/writer để tránh tạo tập dữ liệu pha trộn mới. Dùng test UUID có giá trị cố định qua từng bước migration để phát hiện sai thứ tự byte.

### 10.3. Với thời gian dạng String hoặc Long

Phải xác định ý nghĩa của dữ liệu gốc:

- String có **Z** hoặc offset rõ ràng: có thể parse thành instant.
- String địa phương không có offset/zone: phải chọn **ZoneId theo nguồn dữ liệu**; không tự suy timezone server.
- Long epoch: phải biết đơn vị là **giây, mili giây hay micro giây** trước khi chuyển. Lấy số đó làm milliseconds khi thực tế là seconds có thể tạo ngày sai hoàn toàn.

Ví dụ **$dateFromString** có thể parse văn bản đúng định dạng, nhưng cần chỉ định **format/timezone** khi dữ liệu không có offset và xử lý **onError/onNull**. Đừng xoá trường gốc trước khi đối chiếu kết quả trên bản sao dữ liệu.

## 11. Debug lỗi không thấy kết quả dù không có exception

Một lỗi loại dữ liệu thường âm thầm xuất hiện ở query:

~~~java
// Không đúng với collection nếu paidAt lưu BSON Date:
Query wrong = Query.query(
    Criteria.where("paidAt").gte("2026-11-20T00:00:00Z")
);

// Đúng khi muốn so sánh với thời điểm tuyệt đối:
Query correct = Query.query(
    Criteria.where("paidAt").gte(
        java.util.Date.from(
            java.time.Instant.parse("2026-11-20T00:00:00Z")
        )
    )
);
~~~

Khi dùng **MongoTemplate.find(query, Entity.class)**, mapping có thể chuyển giá trị query tùy kiểu thuộc tính, converter và metadata. Ví dụ trên muốn nhấn mạnh phải **biết BSON được gửi xuống server**, đặc biệt khi truy vấn bằng API thấp hơn, **Document**, raw driver, hoặc trên collection hỗn hợp kiểu. Muốn kết luận đúng, dùng command monitoring/test để kiểm tra BSON query thực sự và chạy mongosh trên document mẫu.

Một tình huống khác: **customerId** trong collection lưu Binary subtype 3 nhưng repository method **findByCustomerId(UUID)** được viết sau khi đổi cấu hình thành STANDARD. Nếu query tìm không thấy, hãy so sánh subtype của field trong database và subtype của tham số mã hóa từ driver. Đừng thay UUID thành **toString()** chỉ vì làm query bắt đầu trả về dữ liệu ở một số bản ghi; việc đó có thể tạo thêm một loại schema mới.

Với truy vấn tiền tệ, kiểm tra BSON type và scale khi tính tổng/so sánh. Một giá trị Double đã bị làm tròn **không thể tự khôi phục chữ số chính xác chỉ bằng cách ép sang Decimal128**; khi cần dữ liệu đúng, phải dựa vào nguồn nghiệp vụ gốc hoặc đối soát độc lập.

## 12. Bài thực hành chẩn đoán

**Bài toán:** collection payments có ba thế hệ bản ghi:

- Phiên bản A ghi **amount** dưới dạng String, **customerId** dạng UUID Java legacy và **paidAt** là chuỗi ngày giờ địa phương.
- Phiên bản B ghi **amount** bằng Double, UUID ở dạng String và **paidAt** bằng BSON Date.
- Phiên bản C dùng contract mới: **Decimal128**, UUID STANDARD subtype 4 và **Instant/BSON Date**.

Yêu cầu:

1. Dùng aggregation **$type** để đếm các nhóm numeric, string và date; ghi kết quả theo từng phiên bản ứng dụng nếu có metadata.
2. Lấy mẫu BSON raw, kiểm tra subtype của **customerId** và phân biệt giá trị UUID đã mã hóa với chuỗi.
3. Kiểm tra giá trị amount có nằm trong giới hạn Decimal128 và có tổn thất từ Double không; liệt kê các bản ghi không thể tự phục hồi chính xác.
4. Viết một test dùng **MongoTemplate** xác nhận contract C: **amount** là Decimal128, **customerId** là Binary subtype 4, **paidAt** là BSON Date.
5. Chỉ định **ZoneId** hợp lệ cho nhóm A dựa trên nguồn dữ liệu; thử ngày biên và so sánh Instant trước/sau.
6. Đề xuất migration theo lô có checkpoint và cập nhật có điều kiện, rồi xác nhận cả ba nhóm sau chuyển đổi truy vấn được bằng Java.

**Tiêu chí đạt:** mọi kết luận dựa trên **BSON type thực tế và quy tắc nghiệp vụ**, có test round-trip; các bản ghi mơ hồ hoặc đã mất precision được đánh dấu cần xử lý thay vì tự tạo giá trị giả.

## 13. Checklist xử lý sự cố

- [ ] Xác định document mẫu, tên field, đường gọi lỗi và nested exception.
- [ ] Kiểm kê **$type**: int/long/double/decimal/string, binData/string, date/string/long/missing.
- [ ] Với UUID, kiểm tra **subtype 3 hoặc 4** và byte order của writer cũ.
- [ ] Với số, kiểm tra range, precision, scale, overflow và converter BigDecimal theo version Spring Data.
- [ ] Với thời gian, xác định rõ epoch unit, UTC instant hay giờ địa phương có ZoneId.
- [ ] Xác nhận **MongoClientSettings.uuidRepresentation** và cấu hình Spring Data Java Time converters.
- [ ] Đọc raw BSON hoặc Extended JSON Canonical để tránh bị lớp mapping che mất kiểu lưu.
- [ ] Viết test round-trip và kiểm tra chính BSON được lưu, kể cả trường null/missing và giá trị biên.
- [ ] Thử migration trên dữ liệu sao chép, giới hạn lô, checkpoint, idempotency và đối soát.
- [ ] Không chuyển sang schema đích trên production nếu còn writer cũ hoặc chưa có phương án khôi phục.

## 14. Tài liệu đối chiếu

1. [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): phân biệt Int32, Int64, Double, Decimal128, Binary, Date và Timestamp.
2. [MongoDB Manual — Comparison/Sort Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/): cách so sánh giữa các BSON type và numeric comparison.
3. [MongoDB Manual — Type Bracketing](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/): điều kiện so sánh theo loại BSON.
4. [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): BigDecimalRepresentation, Java Time converter và targetType.
5. [MongoDB Java Driver — Upgrade Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/): thay đổi mặc định UUID representation và decode subtype.
6. [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): thuộc tính cấu hình UUID của MongoDB.
7. [MongoDB Manual — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/): kiểm tra chuyển đổi dữ liệu số/thời gian và xử lý lỗi.
8. [MongoDB Java Driver — Extended JSON](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-extended-json/): Canonical/Relaxed Extended JSON để phân biệt kiểu dữ liệu.

**Kết luận kỹ thuật:** khi Java và BSON không khớp, sửa đúng nhất bắt đầu từ **xác minh kiểu thực tế**, sau đó chuẩn hóa contract **số / UUID / thời gian**, cấu hình driver và converter tương ứng, rồi chứng minh bằng test **raw BSON + round-trip + query**. Thay đổi entity hoặc cấu hình toàn cục khi chưa kiểm kê dữ liệu cũ dễ biến một lỗi chuyển đổi có thể phát hiện thành sai lệch dữ liệu âm thầm.
