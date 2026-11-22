# Thay đổi cấu hình Boot, kiểu dữ liệu và UUID representation

Nâng phiên bản **Spring Boot** hoặc **Spring Data MongoDB** không chỉ là đổi số version trong file build. Ứng dụng có thể kết nối được nhưng sử dụng sai property, ghi một trường tiền tệ bằng BSON khác trước, hoặc không tìm thấy document vì **UUID representation** thay đổi. Những lỗi này nguy hiểm hơn lỗi khởi động: chúng có thể xuất hiện muộn và khiến dữ liệu cũ, dữ liệu mới không tương thích.

Trong module **SPRING_DATA_MONGODB**, chương **Phiên bản và nâng cấp** tập trung vào một kịch bản cụ thể: chuyển ứng dụng từ **Spring Boot 3.5 / Spring Data MongoDB 4.x** sang **Spring Boot 4.x / Spring Data MongoDB 5.x**. Bài giải thích những thay đổi trong **cấu hình MongoDB**, **kiểu Java/BSON**, **BigDecimal**, **UUID subtype 3 và subtype 4**, sau đó đưa ra cách kiểm tra qua **MongoTemplate**, repository, dữ liệu cũ và MongoDB thật.

**Nguyên tắc xuyên suốt:** nâng cấp framework và chuyển định dạng dữ liệu là **hai thay đổi riêng**. Hãy cố định cách mã hóa/giải mã hiện tại khi nâng framework, đo đạc và kiểm thử; nếu muốn chuẩn hóa schema, thực hiện migration có kế hoạch sau đó.

## 1. Bạn sẽ học được gì?

Sau bài này, bạn có thể:

1. Đối chiếu các property MongoDB quan trọng giữa **Boot 3.5** và **Boot 4.x**.
2. Phân biệt phần cấu hình thuộc **MongoDB Java Driver** với phần thuộc **Spring Data MongoDB**.
3. Chọn rõ cách lưu **BigDecimal/BigInteger** và kiểm tra **BSON String so với Decimal128**.
4. Giải thích vì sao cùng một **UUID Java** có thể thành **Binary subtype 3** hoặc **subtype 4**, và cách giữ tính tương thích với dữ liệu đã lưu.
5. Kiểm tra các thay đổi ở **Instant, LocalDateTime, số nguyên, Double, String, _id**, custom converter và repository query.
6. Thiết kế quá trình nâng cấp có baseline, test round-trip, đối soát, rollout và đường phục hồi.

## 2. Trước tiên, tách bốn lớp phiên bản

| Lớp | Ví dụ | Ảnh hưởng khi nâng |
| --- | --- | --- |
| **Spring Boot** | 3.5 → 4.x | Property binding, auto-configuration, starter/test package, lifecycle và Actuator |
| **Spring Data MongoDB** | 4.x → 5.x | MappingMongoConverter, repository, cấu hình custom conversions, một số API/giá trị mặc định |
| **MongoDB Java Driver** | Driver được BOM của Boot/Spring Data chọn | BSON codec, UuidRepresentation, TLS, connection pool, wire protocol và phiên bản Java hỗ trợ |
| **MongoDB Server + FCV** | Version/FCV hiện tại của cluster | Các toán tử query/aggregation, index, transaction và tính năng server được phép dùng |

**Spring Data MongoDB 5.x yêu cầu MongoDB Java Driver 5.6 trở lên** và không còn hỗ trợ thế hệ driver 4.x. Đây là một yêu cầu theo migration guide của Spring Data 5.x; khi chọn đúng Boot BOM, vẫn cần xem dependency tree để phát hiện một dependency khác ép driver xuống bản không tương thích.

Mỗi lớp có thể thay đổi độc lập. Thí dụ **Spring Boot nâng thành công** nhưng một custom **MongoClient** do ứng dụng tự tạo vẫn đặt **UuidRepresentation.JAVA_LEGACY**, hoặc một service khác ghi UUID bằng STANDARD. Điều cần kiểm chứng là **cấu hình và BSON thực sự được dùng**, không chỉ là thông báo build thành công.

~~~mermaid
flowchart TD
    A["Nâng Spring Boot / Spring Data MongoDB"] --> B["Đối chiếu property và auto-configuration"]
    B --> C["Xác định MongoClient, driver, converters thật"]
    C --> D["Kiểm kê dữ liệu BSON cũ"]
    D --> E{"Đổi representation ngay?"}
    E -- "Không" --> F["Khóa representation tương thích dữ liệu cũ"]
    E -- "Có" --> G["Thiết kế migration riêng + reader/writer chuyển tiếp"]
    F --> H["Repository + integration + round-trip tests"]
    G --> H
    H --> I["Đối soát, rollout, theo dõi và phục hồi"]
~~~

## 3. Những property MongoDB đổi tên khi lên Boot 4

Spring Boot 4 phân biệt rõ hơn **thuộc tính cấu hình MongoDB client** với **thuộc tính thuộc Spring Data**. Phần lớn property kết nối trước đây nằm dưới **spring.data.mongodb** chuyển sang **spring.mongodb**; những property thực sự gắn với repository, converter hoặc mapping vẫn thuộc **spring.data.mongodb**.

| Mục đích | Boot 3.5 | Boot 4.x | Cần chú ý |
| --- | --- | --- | --- |
| Connection URI | **spring.data.mongodb.uri** | **spring.mongodb.uri** | Kiểm tra mọi profile, biến môi trường và test |
| Database | **spring.data.mongodb.database** | **spring.mongodb.database** | Không giả định URI và database riêng luôn được ưu tiên giống nhau |
| Host/port | **spring.data.mongodb.host / port** | **spring.mongodb.host / port** | Chỉ cần khi không dùng URI hoàn chỉnh |
| Username/password | **spring.data.mongodb.username / password** | **spring.mongodb.username / password** | Không commit secret vào repository |
| Authentication database | **spring.data.mongodb.authentication-database** | **spring.mongodb.authentication-database** | Cần đúng khi auth DB khác app DB |
| Replica set name | **spring.data.mongodb.replica-set-name** | **spring.mongodb.replica-set-name** | Đối chiếu với topology thực tế |
| TLS/SSL | **spring.data.mongodb.ssl.enabled / bundle** | **spring.mongodb.ssl.enabled / bundle** | Không tắt certificate verification để chữa lỗi cấu hình |
| UUID | **spring.data.mongodb.uuid-representation** | **spring.mongodb.representation.uuid** | Quan trọng nhất khi collection có UUID |
| Tự tạo index từ mapping | **spring.data.mongodb.auto-index-creation** | **Không đổi** | Không tự bật chỉ vì nâng phiên bản |
| Field naming strategy | **spring.data.mongodb.field-naming-strategy** | **Không đổi** | Thay đổi chiến lược làm khác tên field BSON |
| GridFS bucket/database | **spring.data.mongodb.gridfs.bucket / database** | **Không đổi** | Xem lại nếu dùng GridFS |
| Loại repository | **spring.data.mongodb.repositories.type** | **Không đổi** | Sync/reactive tùy classpath và cấu hình |
| BigDecimal representation | Không có property tương ứng theo cách cấu hình mới của Boot 4 | **spring.data.mongodb.representation.big-decimal** | Chọn tường minh **string** hoặc **decimal128** |
| MongoDB health indicator | **management.health.mongo.enabled** | **management.health.mongodb.enabled** | Kiểm tra Actuator và dashboard |
| MongoDB command/pool metrics | **management.metrics.mongo.command.enabled** và **management.metrics.mongo.connectionpool.enabled** | **management.metrics.mongodb.command.enabled** và **management.metrics.mongodb.connectionpool.enabled** | Kiểm tra metric, alert và dashboard sau đổi tên |

Đây là ánh xạ cho quá trình **Boot 3.5 → Boot 4.x**, không phải quy tắc áp dụng ngược cho mọi bản Boot trong lịch sử. Khi chuyển sang bản patch/minor cụ thể, kiểm tra chính tài liệu **Common Application Properties** của bản đó. Không đoán rằng Boot sẽ luôn bind property cũ sang tên mới bằng cơ chế tương thích tự động.

### 3.1. Ví dụ application.yml trước và sau

**Boot 3.5**, ứng dụng đang dùng UUID Java legacy:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/billing
      uuid-representation: java-legacy
      auto-index-creation: false

management:
  health:
    mongo:
      enabled: true
~~~

**Boot 4.x**, giai đoạn đầu **giữ nguyên định dạng BSON hiện tại**:

~~~yaml
spring:
  mongodb:
    uri: mongodb://localhost:27017/billing
    representation:
      uuid: java-legacy
  data:
    mongodb:
      representation:
        big-decimal: string
      auto-index-creation: false

management:
  health:
    mongodb:
      enabled: true
~~~

Các giá trị trên là **ví dụ môi trường local**. Trong production, dùng secret/connection setting đã được quản trị; không hardcode credential. **uuid: java-legacy** chỉ phù hợp nếu đã xác minh writer cũ dùng Java legacy; **big-decimal: string** chỉ nhằm giữ nguyên định dạng cũ khi dữ liệu BigDecimal trước đó là BSON String.

Nếu collection từ đầu đã lưu UUID subtype 4 và Decimal128, cấu hình Boot 4 thường phù hợp hơn là:

~~~yaml
spring:
  mongodb:
    representation:
      uuid: standard
  data:
    mongodb:
      representation:
        big-decimal: decimal128
~~~

**Không được đổi đồng thời hai cấu hình này trên một database cũ chưa kiểm kê**. Cả hai lựa chọn đều ảnh hưởng đến BSON được ghi và BSON của tham số truy vấn sau khi framework nâng cấp.

### 3.2. Kiểm tra đường tạo MongoClient thực sự

**Spring Boot auto-configuration** áp dụng các property MongoDB lên **MongoClientSettings/MongoClient** do Boot tạo. Nếu ứng dụng tự khai báo **MongoClient bean**, **MongoDatabaseFactory** riêng hoặc custom **MappingMongoConverter**, một phần cấu hình từ application.yml có thể bị bỏ qua hoặc bị ghi đè.

Kiểm tra các trường hợp phổ biến:

1. Ứng dụng sync tạo **MongoTemplate** từ MongoClient nào? Có nhiều MongoClient cho các database không?
2. Ứng dụng reactive tạo **ReactiveMongoTemplate** từ MongoClient nào? Có dùng chung policy UUID hoặc converter với sync không?
3. Có **MongoClientSettingsBuilderCustomizer**, **AbstractMongoClientConfiguration**, **MongoCustomConversions** hoặc custom codec registry không?
4. URI ở application.yml, environment variable, Helm chart, ConfigMap và tham số runtime có cùng giá trị không?
5. Khi chạy test, có **@DynamicPropertySource**, service connection hoặc profile test thay thế URI khác production không?

Đừng kết luận cấu hình UUID đúng chỉ vì property có mặt trong YAML. Hãy viết kiểm thử lưu và đọc bằng đúng bean được service/repository sử dụng.

## 4. BigDecimal, BigInteger và sự khác nhau giữa String với Decimal128

**BigDecimal Java** không xác định duy nhất kiểu BSON ở MongoDB. Trong các thế hệ Spring Data MongoDB trước, BigDecimal/BigInteger thường được ánh xạ thành **BSON String**. Từ **Spring Data MongoDB 5.0**, cấu hình support class **không còn tự chọn default representation** cho hai kiểu này; ứng dụng cần chọn một cách rõ ràng nếu dùng chúng.

| Java | BSON lưu trữ | Ý nghĩa khi truy vấn |
| --- | --- | --- |
| **BigDecimal("12.30")** → String | **"12.30"** | So sánh chuỗi có thứ tự từ điển, khác so sánh số |
| **BigDecimal("12.30")** → Decimal128 | **NumberDecimal("12.30")** | Dùng các phép so sánh/toán tử numeric của MongoDB |
| **Double** | BSON Double | Có rủi ro sai số nhị phân khi dùng cho tiền |
| **Long** | BSON Int64 | Phù hợp số nguyên hoặc đơn vị tiền nhỏ nhất nếu nằm trong giới hạn |

**Ví dụ:** nếu giá trị string **"100"** và **"20"** được sắp xếp tăng dần theo chuỗi thì **"100"** có thể đứng trước **"20"**; với Decimal128, kết quả theo giá trị số là **20 rồi 100**. Thay default converter có thể khiến query, sort, aggregation và index hành xử khác trước, dù entity vẫn khai báo **BigDecimal**.

### 4.1. Giữ BSON String khi mới nâng framework

Nếu mục tiêu của lần triển khai là **nâng Boot/Spring Data trước**, có thể cấu hình:

~~~properties
spring.data.mongodb.representation.big-decimal=string
~~~

Đây là lựa chọn để giữ tương thích với dữ liệu String hiện tại, **không phải khuyến nghị lâu dài cho mọi trường tiền**. Sau khi đã ổn định framework, có thể lên kế hoạch chuyển những field cần truy vấn numeric sang **Decimal128** và đánh giá ảnh hưởng tới index/query.

### 4.2. Dùng Decimal128 có chủ đích

Với một field cụ thể:

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
    private BigDecimal total;

    protected Invoice() {}

    public Invoice(String id, BigDecimal total) {
        this.id = id;
        this.total = total;
    }

    public String getId() { return id; }
    public BigDecimal getTotal() { return total; }
}
~~~

**@Field(targetType = FieldType.DECIMAL128)** nêu rõ kiểu BSON mong muốn cho thuộc tính này. Nếu ứng dụng cần một default khác cho nhiều field, Spring Data 5 còn cho cấu hình **BigDecimalRepresentation** qua **MongoCustomConversions**; lựa chọn đó phải đồng bộ với property Boot và tránh tạo hai cơ chế mâu thuẫn.

**Decimal128 có giới hạn precision/exponent** (34 chữ số có nghĩa). **BigDecimal Java** có thể biểu diễn giá trị nằm ngoài giới hạn này. Đừng chuyển mọi BigDecimal sang Decimal128 mà không kiểm tra giá trị cực lớn và chính sách rounding. Không đổi qua Double trong migration nếu cần giữ số thập phân chính xác.

### 4.3. Kiểm kê kiểu BSON trước khi sửa

~~~javascript
db.invoices.aggregate([
  { $group: { _id: { $type: "$total" }, count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]);

db.invoices.find(
  { total: { $type: "string" } },
  { _id: 1, total: 1 }
).limit(5);

db.invoices.find(
  { total: { $type: "decimal" } },
  { _id: 1, total: 1 }
).limit(5);
~~~

**$type** giúp phân biệt String, Decimal128, Double, Int32, Int64, null và missing ở mức dữ liệu. Nó không tự sửa lỗi nghiệp vụ. Nếu có BSON Double từ trước, chuyển sang Decimal128 **không phục hồi được** phần precision đã mất khi ghi Double.

## 5. UUID representation: subtype 3 và subtype 4

UUID trong Java là **java.util.UUID**, còn MongoDB có thể lưu UUID dưới dạng **BSON Binary**, **BSON String** hoặc cấu trúc tùy ứng dụng. Với BSON Binary, subtype và byte order phải được xác định rõ:

| Representation | BSON binary subtype | Cách mã hóa |
| --- | --- | --- |
| **STANDARD** | **4** | Byte order chuẩn, tương thích đa ngôn ngữ |
| **JAVA_LEGACY** | **3** | Byte order riêng của Java driver legacy |
| **CSHARP_LEGACY** | **3** | Byte order riêng của C# legacy |
| **PYTHON_LEGACY** | **3** | Byte order legacy Python |
| **UNSPECIFIED** | Không chọn định dạng | Driver có thể từ chối encode UUID Java, buộc cấu hình rõ |
| UUID lưu dạng String | BSON String | Không trùng kiểu với bất kỳ Binary subtype nào |

**Subtype 3 chưa đủ để suy ra UUID logic:** với Java/C#/Python legacy, các byte trong subtype 3 có thể được sắp khác nhau. Chuyển raw bytes sang subtype 4 mà không decode bằng đúng representation cũ có thể khiến ID thay đổi.

### 5.1. Tác động khi thay cấu hình

Giả sử một service đã lưu **customerId** bằng **JAVA_LEGACY/subtype 3**. Sau nâng cấp, bạn đặt **uuid: standard**. Một lời gọi repository:

~~~java
// Repository:
// Optional<Customer> findByCustomerId(UUID customerId);

UUID id = UUID.fromString(
    "00112233-4455-6677-8899-aabbccddeeff"
);
repository.findByCustomerId(id);
~~~

Với **STANDARD**, tham số UUID được serialize thành **Binary subtype 4**. Dữ liệu cũ lưu subtype 3 có thể không khớp, dẫn tới **Optional.empty()** dù bản ghi vẫn tồn tại. Một số đường mapping đọc dữ liệu cũ cũng có thể ném lỗi codec/chuyển đổi. Đừng “sửa” bằng cách đổi UUID sang **toString()** trong toàn bộ repository: điều đó tạo ra **BSON String** và có thể làm dữ liệu pha trộn thêm.

**Lựa chọn an toàn ở giai đoạn nâng framework:** giữ lại representation đã được xác minh từ dữ liệu cũ (ví dụ **spring.mongodb.representation.uuid=java-legacy**), kiểm tra hoạt động, rồi lên kế hoạch chuyển sang STANDARD trong một đợt độc lập. Nếu database đã có nhiều representation, phải xây chiến lược đọc/migration cho từng nhóm thay vì kỳ vọng một property xử lý mọi biến thể.

### 5.2. Cấu hình bằng Java driver khi tự tạo client

Nếu ứng dụng tự quản lý **MongoClient**, cần xác nhận thuộc tính cấu hình ở cấp driver:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.UuidRepresentation;

public final class MongoClientFactory {
    private MongoClientFactory() {}

    public static MongoClient createLegacyClient(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .uuidRepresentation(UuidRepresentation.JAVA_LEGACY)
            .build();
        return MongoClients.create(settings);
    }
}
~~~

Đây là ví dụ dùng **JAVA_LEGACY** chỉ cho **giai đoạn tương thích**. Một ứng dụng chỉ ghi dữ liệu mới và đã xác nhận chuẩn STANDARD nên đặt **UuidRepresentation.STANDARD**. Khi Boot auto-configure **MongoClient**, ưu tiên property đúng phiên bản Boot; nếu tự khai báo client, đảm bảo **MongoTemplate**, repositories và **ReactiveMongoTemplate** thực sự dùng client có chính sách tương ứng.

### 5.3. Đọc subtype thực tế bằng BSON thô

Trong **mongosh**, trước tiên xem có bao nhiêu document chứa trường Binary:

~~~javascript
db.customers.aggregate([
  {
    $group: {
      _id: { $type: "$customerId" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

**$type = binData** không phân biệt subtype 3 và 4. Với Java driver, dùng **RawBsonDocument** để đọc không qua entity mapping:

~~~java
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public class UuidBsonProbe {
    public static int subtype(MongoTemplate template, String documentId) {
        RawBsonDocument raw = template.getCollection("customers")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", documentId))
            .first();

        if (raw == null) {
            throw new IllegalStateException("Missing document");
        }
        if (!raw.containsKey("customerId")
                || raw.get("customerId").getBsonType() != BsonType.BINARY) {
            throw new IllegalStateException("customerId is not binary");
        }

        return Byte.toUnsignedInt(raw.getBinary("customerId").getType());
    }
}
~~~

Nếu dùng UUID **làm _id** của document, cần lưu ý query theo _id cũng chịu representation. Trong ví dụ này _id là **String** để việc chẩn đoán không bị ảnh hưởng bởi lỗi UUID ở khóa tìm kiếm.

### 5.4. Chuyển một UUID legacy sang standard đúng cách

Sau khi **chắc chắn** nguồn dữ liệu do Java legacy writer tạo, có thể minh họa phép biến đổi *trong bộ nhớ*:

~~~java
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;

public class UuidMigrationExample {
    public static BsonBinary migrateJavaLegacy(BsonBinary oldValue) {
        if (Byte.toUnsignedInt(oldValue.getType()) != 3) {
            throw new IllegalArgumentException("Expected legacy subtype 3");
        }

        UUID logicalUuid = oldValue.asUuid(UuidRepresentation.JAVA_LEGACY);
        return new BsonBinary(logicalUuid, UuidRepresentation.STANDARD);
    }
}
~~~

Phép chuyển trên **chưa ghi gì vào MongoDB**. Trong migration thực, phải đọc document theo lô, giữ checkpoint, áp dụng update có điều kiện **_id + giá trị BSON cũ** để tránh ghi đè writer đồng thời, rồi đối chiếu rằng cùng UUID logic được phục hồi sau khi ghi subtype 4. Không chạy phép này với C# hoặc Python legacy nếu chưa xác minh byte order nguồn.

## 6. Kiểu thời gian, số và _id cũng cần regression test

UUID và BigDecimal là hai điểm nóng khi nâng Spring Data 5, nhưng **kiểu BSON** nói chung cũng phải được giữ đúng:

| Java/annotation | Kiểu BSON thường gặp | Điều phải kiểm tra |
| --- | --- | --- |
| **Instant** | BSON Date (epoch milliseconds) | UTC và độ chính xác tới mili giây; không giả định lưu nano giây |
| **LocalDateTime** | BSON Date qua converter hoặc chiến lược đã chọn | Dùng UTC hay **ZoneId.systemDefault()**? Giá trị có bị lệch múi giờ? |
| **OffsetDateTime/ZonedDateTime** | Tùy converter của ứng dụng | BSON Date không tự lưu offset/ZoneId ban đầu |
| **Integer** | Int32 | Giá trị biên, chuyển đổi khi dữ liệu cũ là Int64/String |
| **Long** | Int64 | Overflow và quy ước epoch giây hay milli giây nếu chứa thời gian |
| **Double** | Double | Có thể mất độ chính xác thập phân |
| **BigDecimal** | String hoặc Decimal128 | Cấu hình representation và yêu cầu truy vấn |
| **@Id String** | String hoặc ObjectId tùy mapping/conversion | Quy tắc convert chuỗi có dạng ObjectId; test dữ liệu cũ |
| **@MongoId** | Dựa trên kiểu/FieldType khai báo | Cần hiểu khác biệt với quy tắc @Id và _id cũ |

### 6.1. Instant khác LocalDateTime

**Instant** biểu diễn một thời điểm tuyệt đối. **LocalDateTime** chỉ gồm ngày và giờ, **không** có timezone. Khi dùng converter phụ thuộc **system default timezone**, CI chạy UTC và server chạy **Asia/Ho_Chi_Minh** có thể ghi ra hai BSON Date khác nhau từ cùng giá trị LocalDateTime.

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.of(2026, 11, 20, 8, 0);
Instant expected = local
    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .toInstant();

assert expected.equals(Instant.parse("2026-11-20T01:00:00Z"));
~~~

Khi nâng cấp framework, kiểm tra lựa chọn **Spring Data JSR-310 converters** so với **native Java Time codecs**. Quy tắc UTC hoặc timezone hệ thống có thể khác nhau theo cách cấu hình. Với thời điểm tạo/sửa sự kiện, ưu tiên **Instant** và quy ước UTC; nếu cần giữ giờ địa phương hoặc ZoneId gốc, lưu chúng một cách tường minh.

### 6.2. @Id, @MongoId và thay đổi biểu diễn trường khóa

Một khóa Java **String** đôi khi được Spring Data chuyển thành **ObjectId** nếu giá trị có dạng ObjectId hợp lệ và mapping đang dùng **@Id**. Nếu nâng cấp converter hoặc chuyển sang **@MongoId**, cùng một chuỗi có thể được gửi trong filter dưới BSON khác. Kết quả là truy vấn **findById**, update hoặc delete trả rỗng dù document còn tồn tại.

Trước khi thay annotation hay converter, hãy kiểm tra kiểu BSON của **_id**, không sửa schema chỉ vì exception. Nếu collection đã trộn ObjectId và String, cần một quy tắc migration/đọc chuyển tiếp rõ ràng, không được chọn theo cảm tính từ hình thức chuỗi.

## 7. Quy trình kiểm kê hiện trạng trước khi nâng cấp

### 7.1. Lập danh sách cấu hình

Ghi lại những thông tin dưới đây cho **ứng dụng thực sự đang chạy**:

| Nhóm | Bằng chứng nên lưu |
| --- | --- |
| Runtime | Boot, Spring Data MongoDB, Java driver, JDK, BOM và dependency tree |
| MongoDB | Server version, FCV, topology, URI/database thực tế (che secret) |
| Boot | Giá trị property MongoDB ở profile đang dùng, biến môi trường và override |
| Client | MongoClient auto-configured hay custom bean, UUID representation, codec registry |
| Mapping | MappingMongoConverter, MongoCustomConversions, **@Field/@Id/@MongoId**, chiến lược Java Time |
| Schema | Kiểu BSON của các field tiền, UUID, ngày giờ, _id trên dữ liệu cũ |
| Luồng đọc/ghi | Những service, job và batch writer còn dùng phiên bản cũ |
| Query | Các repository method, Criteria, aggregation và index phụ thuộc loại BSON |

**Lưu ý:** chỉ đọc connection string ở dạng được che mật khẩu; không in secret vào báo cáo nâng cấp.

### 7.2. Thống kê BSON gốc bằng MongoDB

Với collection **orders**:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      customerIdType: { $type: "$customerId" },
      createdAtType: { $type: "$createdAt" },
      idType: { $type: "$_id" }
    }
  },
  {
    $group: {
      _id: {
        amount: "$amountType",
        uuid: "$customerIdType",
        time: "$createdAtType",
        id: "$idType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Trong aggregation, **$type** giúp thấy khác biệt **string, decimal, double, long, date, binData, null, missing**. Riêng UUID **binData**, cần thêm kiểm tra subtype trên BSON raw. Khi chạy production có tập dữ liệu lớn, lên kế hoạch thời gian chạy để tránh tăng tải bất ngờ.

Đọc một vài document đại diện bằng Extended JSON Canonical hoặc **RawBsonDocument** để xác nhận, thay vì phụ thuộc vào object Java đã được converter ánh xạ sẵn.

## 8. Viết kiểm thử trước khi đổi version

Một bài test “ứng dụng khởi động được” chưa đủ. Cần tối thiểu ba nhóm:

1. **Contract test BSON:** ghi bằng đúng **MongoTemplate/repository** của ứng dụng và kiểm tra kiểu BSON lưu thật.
2. **Read compatibility test:** đọc document cũ chưa migrate với cấu hình mới; query bằng UUID/BigDecimal và ngày giờ trên dữ liệu cũ.
3. **Integration test:** chạy service, index/query/transaction hoặc reactive flow quan trọng với MongoDB thật, test cả nhánh lỗi.

### 8.1. Entity mẫu và bài test cho Boot 4

Ví dụ entity:

~~~java
package example.upgrade;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("upgrade_probes")
public class UpgradeProbe {
    @Id
    private String id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private UUID customerId;
    private Instant occurredAt;

    protected UpgradeProbe() {}

    public UpgradeProbe(
            String id, BigDecimal amount,
            UUID customerId, Instant occurredAt) {
        this.id = id;
        this.amount = amount;
        this.customerId = customerId;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public UUID getCustomerId() { return customerId; }
    public Instant getOccurredAt() { return occurredAt; }
}
~~~

Trong **Spring Boot 4.0**, annotation **@DataMongoTest** thuộc package **org.springframework.boot.data.mongodb.test.autoconfigure**; trong Boot 3.x, package thường dùng là **org.springframework.boot.test.autoconfigure.data.mongo**. Đây là một ví dụ migration import khi đổi starter/test infrastructure.

~~~java
package example.upgrade;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.mongodb.test.autoconfigure.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest(properties = {
    "spring.mongodb.representation.uuid=standard",
    "spring.data.mongodb.representation.big-decimal=decimal128"
})
class UpgradeProbeBsonContractTest {

    @Autowired MongoTemplate template;

    @Test
    void writesExpectedBsonAndReadsSameLogicalValues() {
        UUID uuid = UUID.fromString(
            "00112233-4455-6677-8899-aabbccddeeff"
        );
        Instant moment = Instant.parse(
            "2026-11-20T01:02:03.123456789Z"
        );
        String id = "upgrade-contract-01";

        template.remove(
            org.springframework.data.mongodb.core.query.Query.query(
                org.springframework.data.mongodb.core.query.Criteria
                    .where("_id").is(id)
            ),
            UpgradeProbe.class
        );
        template.insert(new UpgradeProbe(
            id, new BigDecimal("12.30"), uuid, moment
        ));

        RawBsonDocument raw = template.getCollection("upgrade_probes")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", id))
            .first();
        assertNotNull(raw);
        assertEquals(BsonType.DECIMAL128, raw.get("amount").getBsonType());
        assertEquals(BsonType.BINARY, raw.get("customerId").getBsonType());
        assertEquals(4, Byte.toUnsignedInt(
            raw.getBinary("customerId").getType()
        ));
        assertEquals(BsonType.DATE_TIME, raw.get("occurredAt").getBsonType());

        UpgradeProbe readBack = template.findById(id, UpgradeProbe.class);
        assertNotNull(readBack);
        assertEquals(0, new BigDecimal("12.30")
            .compareTo(readBack.getAmount()));
        assertEquals(uuid, readBack.getCustomerId());
        assertEquals(moment.truncatedTo(ChronoUnit.MILLIS),
            readBack.getOccurredAt());
    }
}
~~~

**Điều kiện chạy:** bài test cần có MongoDB thực từ **Testcontainers** hoặc một database thử nghiệm được cấp riêng, với **spring.mongodb.uri** của Boot 4 đã chỉ đúng endpoint. **@DataMongoTest** chỉ cấu hình test slice, không tự khởi động server trong mọi môi trường. Không dùng chung collection **upgrade_probes** với môi trường production hoặc suite chạy song song nếu fixture chưa được cô lập.

Bài test này kiểm tra **STANDARD/subtype 4**. Để kiểm tra nâng framework mà **giữ dữ liệu Java legacy**, chạy một test tương tự với **uuid=java-legacy**, kỳ vọng subtype **3**; quan trọng hơn, fixture legacy phải được ghi bằng phiên bản cũ hoặc bằng **BsonBinary(UUID, JAVA_LEGACY)**, rồi đọc lại bằng ứng dụng mới. Trường hợp này phát hiện lỗi migration mà test dữ liệu mới không thấy.

### 8.2. Ma trận hồi quy tối thiểu

| Trường hợp | Bằng chứng cần đạt |
| --- | --- |
| Boot 3.5 đọc/ghi BSON cũ | Lưu baseline kiểu BSON và kết quả truy vấn |
| Boot 4 cấu hình giống dữ liệu cũ | Đọc cùng document, query UUID cũ, lưu đúng subtype/format |
| Boot 4 STANDARD trên dữ liệu đã chuyển | UUID subtype 4, query và round-trip đúng |
| BigDecimal String cũ | Đọc được khi chọn chế độ giữ tương thích; sort/query theo quy tắc dữ liệu cũ |
| BigDecimal Decimal128 mới | BSON decimal, không làm tròn trái quy định; aggregation số đúng |
| LocalDateTime các timezone khác nhau | Không có lệch thời điểm ngoài quy tắc nghiệp vụ |
| Long/Integer/_id | Giá trị biên và kiểu BSON của khóa không đổi ngoài dự kiến |
| Reactive repository/MongoTemplate | Publisher được subscribe và đọc/ghi thực, không chỉ tạo Mono/Flux |
| Index, transaction, aggregation | Chạy đúng trên topology và server/FCV dự kiến |

Không khẳng định “đã tương thích” từ một unit test mock repository, vì mock không mã hóa tham số UUID hoặc đọc BSON thật.

## 9. Kế hoạch nâng cấp từng giai đoạn, có thể phục hồi

**Giai đoạn A — Khảo sát và chốt contract**

1. Ghi version thực tế của Boot, Spring Data, driver, server và FCV.
2. Kiểm kê từng field nhạy cảm: BSON type, UUID subtype, timezone, index và giá trị biên.
3. Xác định có những service, batch job hoặc ứng dụng khác còn ghi format cũ hay không.
4. Lưu test fixture gồm dữ liệu từ bản cũ, đặc biệt UUID Java legacy và amount String.

**Giai đoạn B — Nâng framework, giữ BSON cũ**

1. Đổi property sang namespace Boot 4; cấu hình UUID và BigDecimal **theo dữ liệu đang tồn tại**.
2. Kiểm tra BOM, các starter và API/import thay đổi; không ép driver 4.x đi cùng Spring Data 5.x.
3. Kiểm tra MongoClient đang dùng, SSL/auth, mapping converter và index migration.
4. Chạy unit, repository, integration, round-trip test và đọc dữ liệu cũ thật trên staging.

**Giai đoạn C — Chuyển dữ liệu nếu có mục tiêu mới**

1. Chỉ sau khi triển khai ổn định mới lập migration từ UUID subtype 3 sang subtype 4 hoặc BigDecimal String sang Decimal128.
2. Thử trên bản sao dữ liệu; xác định dữ liệu không chuyển đổi được, phương án retry và rollback.
3. Migration theo lô, lưu checkpoint **sau khi lô thành công**, dùng update có điều kiện dựa trên giá trị BSON cũ.
4. Phối hợp writer để tránh phát sinh dữ liệu pha trộn trong lúc chuyển; sau đó chuyển config toàn hệ thống về STANDARD/DECIMAL128.
5. Đối soát lại số lượng, BSON type, UUID logic, giá trị tiền và truy vấn.

**Giai đoạn D — Chốt schema mới**

Chỉ xóa converter/reader tương thích legacy khi không còn dữ liệu cũ hay writer cũ. Đặt kiểm thử BSON contract trong CI để những lần nâng cấp tiếp theo không vô tình đưa subtype 3 hoặc String trở lại.

**Lưu ý về rollback:** sau khi dữ liệu mới được ghi ở subtype 4 hoặc Decimal128, việc rollback artifact về phiên bản cũ có thể khiến phiên bản đó đọc không đúng. Phương án phục hồi phải xét cả **ứng dụng và schema BSON**, không chỉ khả năng deploy lại JAR cũ.

## 10. Những sai lầm dễ gây lỗi âm thầm

| Cách làm | Vì sao không an toàn | Thay bằng |
| --- | --- | --- |
| Chỉ đổi version rồi chạy smoke test kết nối | Không kiểm tra truy vấn, codec và dữ liệu cũ | Test round-trip và query trên fixture BSON cũ |
| Đặt **uuid=standard** khi có legacy subtype 3 | Tham số query khác binary subtype, có thể không khớp | Giữ representation cũ để nâng framework trước, migrate riêng |
| Đổi Byte subtype 3 thành 4 bằng thao tác bytes trực tiếp | Byte order legacy có thể khác | Decode bằng representation gốc, encode STANDARD |
| Đặt **big-decimal=decimal128** với String chưa migrate | Có thể đổi kết quả query/sort và dữ liệu mới | Phân tích schema rồi migrate có kiểm soát |
| Đổi **@Id** sang **@MongoId** mà không kiểm tra BSON _id | Khóa truy vấn có thể đổi String/ObjectId | Thử fixture _id hiện tại và định nghĩa rõ khóa đích |
| Dựa vào timezone máy chủ cho LocalDateTime | Dev/CI/prod có timezone khác nhau | Quy ước Instant/ZoneId và converter nhất quán |
| Chỉ sửa application.yml mà bỏ custom MongoClient | Custom bean có thể không dùng property mới | Xác minh client, codec, converters được gọi thực |
| Bật auto-index-creation theo thói quen | Có thể thay chi phí startup và index trên production | Quản lý index migration riêng và đo ảnh hưởng |
| Không cập nhật dashboard Actuator | Health/metrics đổi tên, alert mất tín hiệu | Cập nhật config, metric query và kiểm thử observability |

### Ví dụ lỗi thực tế: dữ liệu cũ mất khỏi truy vấn

Trước nâng cấp, collection **customers** có **customerId** BSON Binary subtype 3, ứng dụng chạy với Java legacy. Sau nâng cấp, service báo “không tìm thấy khách hàng” nhưng mongosh vẫn hiển thị document.

Trình tự xử lý đúng:

1. Kiểm tra **$type** cho customerId; đọc raw subtype và biết writer nào tạo dữ liệu.
2. Xác nhận MongoClient của service hiện tại đang encode UUID dạng nào; test một UUID cố định.
3. Nếu dữ liệu gốc là JAVA_LEGACY, sửa cấu hình Boot 4 thành **spring.mongodb.representation.uuid=java-legacy** để khôi phục tương thích trước.
4. Bổ sung regression test đọc/ghi cùng UUID trước và sau nâng framework.
5. Nếu muốn STANDARD, lên lịch migration riêng và chuyển các reader/writer phối hợp.

Đây là lỗi **biểu diễn BSON/codec**, không phải lỗi mất document hoặc lỗi index. Xóa index và rebuild không làm subtype 3 biến thành subtype 4.

## 11. Checklist trước khi merge hoặc triển khai

- [ ] Đã đối chiếu **Boot 3.5 → Boot 4.x** property MongoDB, health/metrics và profile overrides.
- [ ] Đã chốt phiên bản **Spring Data MongoDB 5.x / Java Driver 5.6+** phù hợp với BOM.
- [ ] Đã kiểm tra MongoClient thực tế, đặc biệt mọi custom bean, sync/reactive và codec registry.
- [ ] Đã kiểm kê **BSON String/Decimal128/Double**, UUID subtype **3/4**, BSON Date, null/missing và _id.
- [ ] UUID representation được cấu hình **tường minh** theo dữ liệu hiện tại.
- [ ] BigDecimalRepresentation được cấu hình **tường minh**; không ngầm đổi từ String sang Decimal128.
- [ ] Đã chạy repository/integration test đọc dữ liệu **do phiên bản cũ ghi**, không chỉ ghi dữ liệu mới.
- [ ] Đã kiểm tra query/aggregation/index/transaction và thời gian theo zone.
- [ ] Nếu đổi schema, có migration theo lô với checkpoint, điều kiện ghi an toàn và đối soát.
- [ ] Có phương án rollout/rollback gắn với **schema BSON**, alert và health/metrics mới.

## 12. Bài thực hành

**Bối cảnh:** một service thanh toán chạy Spring Boot 3.5, lưu **amount** dạng String, **customerId** bằng **JAVA_LEGACY** và **createdAt** dạng BSON Date. Team muốn lên Boot 4, sau đó chuyển amount thành Decimal128 và UUID thành STANDARD.

**Yêu cầu:**

1. Viết bản đồ property cho hai phiên bản Boot, gồm Mongo URI, UUID representation, BigDecimal representation và auto-index-creation.
2. Tạo hai document test: một document dạng legacy, một document dạng standard. Dùng BSON raw xác minh **amount** và **customerId** của từng document.
3. Kiểm tra ứng dụng Boot 4 cấu hình **java-legacy/string** đọc document legacy và truy vấn bằng UUID thành công.
4. Viết test cho schema mới với **decimal128/standard**, kiểm tra subtype 4 và round-trip.
5. Giải thích vì sao chỉ đổi property của application.yml **không** tự di trú BSON cũ, và vì sao không thể thay byte subtype trực tiếp.
6. Thiết kế migration theo lô có checkpoint, xử lý writer đồng thời, rollback và đối soát.

**Tiêu chí hoàn thành:** kết quả test chứng minh kiểu BSON thực tế, giá trị Java sau khi đọc, hành vi query và kế hoạch nâng cấp tách biệt với chuyển dữ liệu. Mỗi quyết định representation đều có căn cứ từ dữ liệu đang được lưu.

## 13. Tài liệu tham khảo chính thức

1. [Spring Boot — 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): property MongoDB chuyển namespace, thay đổi UUID/BigDecimal, Actuator và module.
2. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): đối chiếu tên property ở bản cũ.
3. [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/): xác minh tên property và default ở bản đích.
4. [Spring Data MongoDB — Migration Guide 4.x to 5.x](https://docs.spring.io/spring-data/mongodb/reference/migration-guide/migration-guide-4.x-to-5.x.html): yêu cầu driver, thay đổi UUID và BigDecimal.
5. [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/data-mongo/reference/5.0/mongodb/mapping/custom-conversions.html): BigDecimalRepresentation, converter, Java Time và targetType.
6. [MongoDB — BSON Binary UUID Specification](https://github.com/mongodb/specifications/blob/master/source/bson-binary-uuid/uuid.md): subtype 3/4, byte order và chế độ UNSPECIFIED.
7. [MongoDB Java Driver — BsonBinary API](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/bson/org/bson/BsonBinary.html): chuyển đổi UUID theo representation tường minh.
8. [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): Decimal128, Binary, Date, Int32/Int64 và các kiểu khác.
9. [Spring Boot 4.0 — DataMongoTest API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/mongodb/test/autoconfigure/DataMongoTest.html): test slice và package trong Boot 4.

**Ghi nhớ:** mục tiêu an toàn của lần nâng cấp đầu tiên là **cùng dữ liệu BSON, cùng UUID logic, cùng kết quả truy vấn** sau khi đổi framework. Nếu muốn chuyển String sang Decimal128 hay legacy UUID sang STANDARD, phải đối xử với đó như một **migration dữ liệu độc lập, có kiểm thử và đối soát**.
